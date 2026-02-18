"""
Rhino Dynamic Blocks Utility (RhinoPython)

A lightweight dynamic-block system for Rhinoceros inspired by AutoCAD dynamic blocks.
It lets you:
1) define a parametric "family"
2) insert instances with parameter values
3) update existing instances by editing parameters

Supported family type in this MVP: Rectangle (planar polyline) with Width and Height.
"""

import json
import uuid

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

STORE_SECTION = "RhinoDynamicBlocks"
STORE_KEY = "Registry"


class Family(object):
    def __init__(self, family_id, name, family_type, parameters):
        self.family_id = family_id
        self.name = name
        self.family_type = family_type
        self.parameters = parameters


class DynamicBlockRegistry(object):
    def __init__(self, doc):
        self.doc = doc
        self.data = self._load()

    def _load(self):
        raw = self.doc.Strings.GetValue(STORE_SECTION, STORE_KEY)
        if not raw:
            return {"families": {}, "instances": {}}
        try:
            loaded = json.loads(raw)
            loaded.setdefault("families", {})
            loaded.setdefault("instances", {})
            return loaded
        except Exception:
            return {"families": {}, "instances": {}}

    def save(self):
        self.doc.Strings.SetString(STORE_SECTION, STORE_KEY, json.dumps(self.data))

    def add_family(self, family):
        self.data["families"][family.family_id] = {
            "name": family.name,
            "family_type": family.family_type,
            "parameters": family.parameters,
        }
        self.save()

    def get_family(self, family_id):
        return self.data["families"].get(family_id)

    def find_family_by_name(self, name):
        for family_id, family in self.data["families"].items():
            if family["name"].lower() == name.lower():
                return family_id, family
        return None, None

    def add_instance(self, obj_id, family_id, values):
        self.data["instances"][str(obj_id)] = {"family_id": family_id, "values": values}
        self.save()

    def get_instance(self, obj_id):
        return self.data["instances"].get(str(obj_id))

    def remove_instance(self, obj_id):
        self.data["instances"].pop(str(obj_id), None)
        self.save()

    def iter_instances_for_family(self, family_id):
        for obj_id, info in self.data["instances"].items():
            if info["family_id"] == family_id:
                yield obj_id, info


# ---------- Geometry factories ----------

def make_rectangle_geometry(width, height):
    p0 = Rhino.Geometry.Point3d(0, 0, 0)
    p1 = Rhino.Geometry.Point3d(width, 0, 0)
    p2 = Rhino.Geometry.Point3d(width, height, 0)
    p3 = Rhino.Geometry.Point3d(0, height, 0)
    poly = Rhino.Geometry.Polyline([p0, p1, p2, p3, p0])
    return [poly.ToNurbsCurve()]


def build_geometry(family_type, values):
    if family_type == "rectangle":
        return make_rectangle_geometry(float(values["Width"]), float(values["Height"]))
    raise ValueError("Unsupported family type: {}".format(family_type))


# ---------- Block definition helpers ----------

def definition_name(family_name, values):
    payload = "_".join("{}={}".format(k, values[k]) for k in sorted(values.keys()))
    return "DB_{}_{}".format(family_name, payload)


def ensure_definition(doc, family, values):
    name = definition_name(family["name"], values)
    idef = doc.InstanceDefinitions.Find(name, True)
    if idef:
        return idef.Index

    geometry = build_geometry(family["family_type"], values)
    base_point = Rhino.Geometry.Point3d(0, 0, 0)
    attrs = [doc.CreateDefaultAttributes() for _ in geometry]
    idx = doc.InstanceDefinitions.Add(name, "Dynamic block variant", base_point, geometry, attrs)
    return idx


def replace_instance_geometry(doc, instance_id, family, values):
    obj_ref = doc.Objects.FindId(Rhino.Guid(instance_id))
    if obj_ref is None:
        return False

    inst_obj = obj_ref
    if not isinstance(inst_obj, Rhino.DocObjects.InstanceObject):
        return False

    xform = inst_obj.InstanceXform
    attr = inst_obj.Attributes.Duplicate()

    if not doc.Objects.Delete(inst_obj, False):
        return False

    idef_index = ensure_definition(doc, family, values)
    new_id = doc.Objects.AddInstanceObject(idef_index, xform, attr)
    if new_id == Rhino.Guid.Empty:
        return False

    return str(new_id)


# ---------- Commands ----------

def cmd_create_rectangle_family():
    name = rs.GetString("Family name", "DoorPanel")
    if not name:
        return

    default_w = rs.GetReal("Default Width", 1.0, 0.001)
    if default_w is None:
        return

    default_h = rs.GetReal("Default Height", 2.1, 0.001)
    if default_h is None:
        return

    reg = DynamicBlockRegistry(sc.doc)
    existing_id, _ = reg.find_family_by_name(name)
    if existing_id:
        rs.MessageBox("Family '{}' already exists".format(name), 0, "Dynamic Blocks")
        return

    family = Family(
        family_id=str(uuid.uuid4()),
        name=name,
        family_type="rectangle",
        parameters={"Width": default_w, "Height": default_h},
    )
    reg.add_family(family)
    rs.MessageBox("Created family '{}'".format(name), 0, "Dynamic Blocks")


def cmd_insert_instance():
    reg = DynamicBlockRegistry(sc.doc)
    families = reg.data.get("families", {})
    if not families:
        rs.MessageBox("No families found. Create one first.", 0, "Dynamic Blocks")
        return

    names = sorted([f["name"] for f in families.values()])
    name = rs.ListBox(names, "Pick family", "Dynamic Blocks")
    if not name:
        return

    family_id, family = reg.find_family_by_name(name)
    if not family:
        return

    width = rs.GetReal("Width", float(family["parameters"]["Width"]), 0.001)
    if width is None:
        return
    height = rs.GetReal("Height", float(family["parameters"]["Height"]), 0.001)
    if height is None:
        return

    pt = rs.GetPoint("Insertion point")
    if not pt:
        return

    values = {"Width": round(width, 6), "Height": round(height, 6)}
    idef_index = ensure_definition(sc.doc, family, values)
    xform = Rhino.Geometry.Transform.Translation(pt.X, pt.Y, pt.Z)
    obj_id = sc.doc.Objects.AddInstanceObject(idef_index, xform)
    if obj_id == Rhino.Guid.Empty:
        rs.MessageBox("Failed to create instance", 0, "Dynamic Blocks")
        return

    reg.add_instance(str(obj_id), family_id, values)
    sc.doc.Views.Redraw()


def cmd_edit_instance_parameters():
    reg = DynamicBlockRegistry(sc.doc)
    obj_id = rs.GetObject("Pick dynamic block instance", rs.filter.instance)
    if not obj_id:
        return

    inst = reg.get_instance(str(obj_id))
    if not inst:
        rs.MessageBox("Selected instance is not managed by Dynamic Blocks.", 0, "Dynamic Blocks")
        return

    family = reg.get_family(inst["family_id"])
    if not family:
        rs.MessageBox("Family metadata missing.", 0, "Dynamic Blocks")
        return

    cur_vals = inst["values"]
    width = rs.GetReal("Width", float(cur_vals["Width"]), 0.001)
    if width is None:
        return
    height = rs.GetReal("Height", float(cur_vals["Height"]), 0.001)
    if height is None:
        return

    new_values = {"Width": round(width, 6), "Height": round(height, 6)}
    new_id = replace_instance_geometry(sc.doc, str(obj_id), family, new_values)
    if not new_id:
        rs.MessageBox("Failed to update instance", 0, "Dynamic Blocks")
        return

    reg.remove_instance(str(obj_id))
    reg.add_instance(new_id, inst["family_id"], new_values)
    sc.doc.Views.Redraw()


def cmd_sync_family_instances():
    reg = DynamicBlockRegistry(sc.doc)
    families = reg.data.get("families", {})
    if not families:
        rs.MessageBox("No families available.", 0, "Dynamic Blocks")
        return

    names = sorted([f["name"] for f in families.values()])
    name = rs.ListBox(names, "Pick family to update all instances", "Dynamic Blocks")
    if not name:
        return

    family_id, family = reg.find_family_by_name(name)
    if not family:
        return

    default_w = rs.GetReal("New default Width", float(family["parameters"]["Width"]), 0.001)
    if default_w is None:
        return
    default_h = rs.GetReal("New default Height", float(family["parameters"]["Height"]), 0.001)
    if default_h is None:
        return

    family["parameters"]["Width"] = round(default_w, 6)
    family["parameters"]["Height"] = round(default_h, 6)

    updates = []
    for obj_id, info in list(reg.iter_instances_for_family(family_id)):
        updates.append((obj_id, info))

    for obj_id, info in updates:
        # Keep per-instance values, unless you want global reset.
        if not sc.doc.Objects.FindId(Rhino.Guid(obj_id)):
            reg.remove_instance(obj_id)
            continue

        new_id = replace_instance_geometry(sc.doc, obj_id, family, info["values"])
        if new_id and new_id != obj_id:
            reg.remove_instance(obj_id)
            reg.add_instance(new_id, family_id, info["values"])

    reg.save()
    sc.doc.Views.Redraw()
    rs.MessageBox("Family '{}' synchronized.".format(name), 0, "Dynamic Blocks")


def run():
    options = [
        "CreateRectangleFamily",
        "InsertInstance",
        "EditInstance",
        "SyncFamily",
    ]
    choice = rs.ListBox(options, "Choose Dynamic Blocks action", "Dynamic Blocks")
    if choice == "CreateRectangleFamily":
        cmd_create_rectangle_family()
    elif choice == "InsertInstance":
        cmd_insert_instance()
    elif choice == "EditInstance":
        cmd_edit_instance_parameters()
    elif choice == "SyncFamily":
        cmd_sync_family_instances()


if __name__ == "__main__":
    run()
