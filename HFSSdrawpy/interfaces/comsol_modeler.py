# -*- coding: utf-8 -*-
"""
Created on Tue Feb  9 16:04:58 2021

@author: Alexandre

Next things to do :
    - Assign lumped RLC
    - Refine mesh (assign mesh length)
    - Draw wirebond
"""

import os
import os.path as osp
import signal
import subprocess
from collections import namedtuple
from functools import wraps
from xml.parsers.expat import model

import mph

# Bizarre d'importer drawpylib dans hfssdrawpy
from .. import parameters as layer_ids
from ..core.entity import gen_name
from ..utils import Vector, parse_entry, val


class ComsolModeler:
    client = None
    comsol_version = "6.4"
    server_port = 2036

    def __init__(self, number_of_cores=1, save_path=None, gui=False):
        """Comsol Modeler opens a Comsol server listening on port 2036
        and a comsol client connected to that server.
        Then it opens the Comsol GUI if neede to follow the model modifications
        One just needs to connect the session to the server in the gui:
            File/Comsol Multiphysics server/connect to server
        And to import the running model:
            File/Comsol Multiphysics server/import application from server
        """

        self._number_of_cores = number_of_cores

        # Run server
        #### self.server = mph.Server(cores=number_of_cores)
        #### print(f"Comsol server started listening on port {self.server_port}")

        # Connect client to server
        if self.client is None:
            try:
                ComsolModeler.client = mph.Client(
                    cores=number_of_cores, version=self.comsol_version, port=self.server_port
                )
            except BaseException:
                raise RuntimeError(
                    r"could not connect to server: browse to "
                    r"C:\Program Files\COMSOL\COMSOL56\Multiphysics\COMSOL Launchers"
                    r"and launch 'COMSOL Multiphysics Server 5.6'."
                    r"You should also restart this Kernel before attempting to reconnect"
                    r"Launch 'COMSOL Multiphysics Client 5.6' and connect to the same"
                    r"server to check your model in real time. Don't forget to import the"
                    r"current application via file->COMSOL Multiphysics Server->Import application from server"
                )
        print(f"Comsol client (v{self.comsol_version}) connected to server")

        # Save current model
        if save_path is None:
            self._save_path = osp.join(
                osp.dirname(__file__), "MyModel.mph"
            )  # str(Path.home().joinpath('MyModel.mph'))
        # self.pymodel = self.client.create(self.save_path)
        # Saves in order to reload using the MPh library
        ### self.pymodel.java.save(self.save_path)
        # Remove model from client before loading it again...
        # This is needed due to the way MpH works (model.py is instantiated
        # by loading a .mph file)
        # self.client.remove(self.pymodel)
        # print(f"Comsol model saved in {self.save_path}")

        # Start GUI
        if gui:
            self.start_gui()

        if len(self.client.models()) == 0:
            self.model = self.client.load(self.save_path)
        # Load model using Mph module
        self.model = self.client.models()[-1]

        ### Remove e

        ### self.model = self.client.load(self.save_path)
        #

        self.deleted_entities = []

        # dict containing the number of transforms having been applied to a
        # given entity. Every new transformation is named tN_name where name
        # is the actual entity name and N-1 the number of transforms it has
        # already experienced.
        # New trasnforms should always be applied to self._last_transfrom_name(name)
        self.transforms = {}

        import com  # # can be done once the JVM has been started by instantiating mph.Client...

        try:
            self.model.java.component().remove("main_comp")
        except com.comsol.util.exceptions.FlException:
            pass

        self.model.java.component().create("main_comp", True)

        self.main_comp = self.model.java.component("main_comp")

        self.main_comp.geom().create("main_geom", 3)
        self.main_geom = self.main_comp.geom("main_geom")

        # two workplanes are created : one for all physical components (main_wp)
        # and one for MESH and PORT layers
        self.main_wp = self.main_geom.create("main_wp", "WorkPlane")
        self.main_geom.feature().move("main_wp", 0)

        self.main_wp_entities = []
        self.mesh_port_wp = self.main_geom.create("mesh_port_wp", "WorkPlane")
        self.main_geom.feature().move("mesh_port_wp", 1)

        # self.main_comp.mesh().create("main_mesh")

        # PEC assignment is tricky, we create a selection "pec_sel" in the main wp,
        # and make it visible from the physics by setting "selplaneshow" to "on"
        # the boundaries belonging to pec_sel are then the input of a PEC in the physics

        # This was the theory, for the moment let's just create the selection

        # self.emw_physics = self.main_comp.physics().create("emw", "ElectromagneticWaves", "emw_geom")
        # self.pec = self.emw_physics.create("pec", "PerfectElectricConductor", 2)
        self.pec_sel = self.main_wp.geom().selection().create("pec_sel", "CumulativeSelection")
        # self.main_wp.set("selplaneshow", "on")
        # self.pec.selection().named("main_geom_main_wp_pec_sel_bnd")

        # Comsol fails to read to long expressions, so we create intermediray parameters in a second table
        # elf.inter_params = self.model.java.param().group().create("inter_params")

        self.objects = {}
        self.main_geom.run()

    def start_gui(self):
        """Starts the COMSOL GUI"""
        info = mph.discovery.backend()
        self.gui = subprocess.Popen(
            str(info["root"].joinpath("bin", "comsol")),
            stdout=subprocess.PIPE,
            shell=True,
            preexec_fn=os.setsid,
        )
        print(
            """You can now manually connect the GUI to the server:
              File/Comsol Multiphysics server/connect to server
        and import the current model in the GUI:
              File/Comsol Multiphysics server/import application from server"""
        )

    def close_gui(self):
        os.kill(self.p.pid, signal.CTRL_C_EVENT)
        os.killpg(os.getpgid(self.gui.pid), signal.SIGTERM)
        print("GUI closed")

    def close(self):
        """Disconnects client from server, closes server,
        and exits gui in a clean way"""
        try:
            self.client.disconnect()
            print("Client disconnected")
        except RuntimeError:
            pass
        try:
            self.server.stop()
            print("Server stopped")
        except RuntimeError:
            pass
        try:
            self.close_gui()
        except RuntimeError:
            pass

    # Read-only variables
    @property
    def number_of_cores(self):
        return self._number_of_cores

    @property
    def save_path(self):
        return self._save_path

    def evaluate(self, expr: str):
        """
        Evaluates a comsol expression and returns a float.
        """
        # We use the raw java interface here as mph doesn't implement this part of the comsol api yet
        return self.model.java.param().evaluate(expr)

    def set_variable(self, name, value):
        """The parameter is added in the main param table, which is the only
        one that should be used in the GUI"""

        def hfss_to_comsol(s):
            """Transforms '25um' into '25[um]"""
            numerics = "0123456789.e+-"
            ind_unit = [i for i, c in enumerate(str(s)) if c not in numerics]
            if ind_unit:
                val = s[: ind_unit[0]]
                unit = s[ind_unit[0] :]
                return f"{val}[{unit}]"
            else:  # Case when no unit
                return s

        if isinstance(value, str):
            self.model.parameter(name, hfss_to_comsol(value))
        else:
            self.model.parameter(name, str(value))

    def create_coor_sys(self, *args, **kwargs):
        """Only uselful in hfss"""
        pass

    def set_coor_sys(self, *args, **kwargs):
        """Only uselful in hfss"""
        pass

    def assert_name(func):
        """Decorator checking the coherence of the entity's name"""

        @wraps(func)
        def asserted_name(*args, **kwargs):
            name = func(*args, **kwargs)
            msg = "Failed at generating a name for %s" % name
            assert name == kwargs["name"], msg
            return name

        return asserted_name

    @assert_name
    def box(self, pos, size, **kwargs):
        """/!\ The rotate and translate methods are not implemented for 3D objects in Comsol yet! /!\ """

        if len(pos) == 2:
            pos.append(0)
        if len(size) == 2:
            size.append(0)
        pos = parse_entry(pos)
        pos_strs = self._sympy_to_comsol_str(*pos)
        size = parse_entry(size)
        size_strs = self._sympy_to_comsol_str(*size)
        name = kwargs["name"]

        comsol_size = []
        comsol_pos = []

        # Comsol does not support negative sizes, so this is dealt with here
        for i, s in enumerate(size_strs):
            if self.evaluate(s) < 0:
                comsol_size.append("-(" + size_strs[i] + ")")
                comsol_pos.append(pos_strs[i] + "+" + size_strs[i])
            else:
                comsol_size.append(size_strs[i])
                comsol_pos.append(pos_strs[i])

        box = self.main_geom.create(name, "Block")
        for i, cs in enumerate(comsol_size):
            box.setIndex("size", cs, i)
        for i, cp in enumerate(comsol_pos):
            box.setIndex("pos", cp, i)
        return name

    @assert_name
    def box_center(self, pos, size, **kwargs):
        pos = parse_entry(pos)
        size = parse_entry(size)
        corner_pos = [val(p) - val(s) / 2 for p, s in zip(pos, size)]
        return self.box(corner_pos, size, **kwargs)

    @assert_name
    def rect(self, pos, size, **kwargs):

        rectangle_name = kwargs["name"]
        layer = kwargs["layer"]

        # Add 0 component if 2D vectors to make them 3D and parse
        pos, size = self._make_3D(pos, size)
        pos, size = parse_entry(pos, size)

        # Generate Comsol strings from Sympy expressions
        size_0, size_1 = self._sympy_to_comsol_str(size[0], size[1])
        pos_0, pos_1 = self._sympy_to_comsol_str(pos[0], pos[1])

        # Ensure that width and height are positiv (Comsol don't like if <0)
        pos_x, width = self._make_positiv(pos_0, size_0)
        pos_y, height = self._make_positiv(pos_1, size_1)

        # If the rectangle is in the MESH or PORT layer, it should be added to the specific workplane
        wp = self._set_workplane(layer, rectangle_name)

        rect = wp.geom().create(rectangle_name, "Rectangle")
        self.model.parameter(f"{rectangle_name}_width", width)
        self.model.parameter(f"{rectangle_name}_height", height)
        self.model.parameter(f"{rectangle_name}_pos_x", pos_x)
        self.model.parameter(f"{rectangle_name}_pos_y", pos_y)
        rect.setIndex("size", f"{rectangle_name}_width", 0)
        rect.setIndex("size", f"{rectangle_name}_height", 1)
        rect.setIndex("pos", f"{rectangle_name}_pos_x", 0)
        rect.setIndex("pos", f"{rectangle_name}_pos_y", 1)

        self.objects[rect.tag()] = rect

        print(f"Rectangle {rectangle_name} created")

        return rectangle_name

    @assert_name
    def disk(self, pos, radius, axis, **kwargs):

        disk_name = kwargs["name"]
        layer = kwargs["layer"]

        # Generate Comsol strings from Sympy expressions
        radius = self._sympy_to_comsol_str(radius)[0]
        pos_x, pos_y = self._sympy_to_comsol_str(pos[0], pos[1])

        # If the rectangle is in the MESH or PORT layer, it should be added to the specific workplane
        wp = self._set_workplane(layer, disk_name)

        disk = wp.geom().create(disk_name, "Circle")
        disk.set("r", radius)
        self.model.parameter(f"{disk_name}_pos_x", pos_x)
        self.model.parameter(f"{disk_name}_pos_y", pos_y)
        disk.setIndex("pos", f"{disk_name}_pos_x", 0)
        disk.setIndex("pos", f"{disk_name}_pos_y", 1)

        self.objects[disk.tag()] = disk

        print(f"Disk {disk_name} created")

        return disk_name

    @assert_name
    def rect_center(self, pos, size, **kwargs):
        pos = parse_entry(pos)
        size = parse_entry(size)
        corner_pos = [val(p) - val(s) / 2 for p, s in zip(pos, size)]
        name = self.rect(corner_pos, size, **kwargs)
        return name

    @assert_name
    def polyline(self, points, closed=True, **kwargs):

        polygon_name = kwargs["name"]
        layer = kwargs["layer"]

        for i in range(len(points)):
            if isinstance(points[i], tuple) and len(points[i]) == 2:
                points[i] += (0,)
            elif isinstance(points[i], list) and len(points[i]) == 2:
                points[i].append(0)

        points = parse_entry(points)

        wp = self._set_workplane(layer, polygon_name)

        pol = wp.geom().create(polygon_name, "Polygon")
        pol.set("source", "table")

        if closed:
            pol.set("type", "solid")
        else:
            pol.set("type", "open")

        from tqdm import tqdm

        for ii, point in enumerate(tqdm(points)):
            # pol.setIndex("table", self._sympy_to_comsol_str(point[0]), ii, 0)
            # pol.setIndex("table", self._sympy_to_comsol_str(point[1]), ii, 1)
            import jpype

            pol.setIndex("table", self._sympy_to_comsol_str(point[0])[0], jpype.JInt(ii), 0)
            pol.setIndex("table", self._sympy_to_comsol_str(point[1])[0], jpype.JInt(ii), 1)

        print("Polygon {} created".format(polygon_name))

        return polygon_name

    def sweep_along_path(self, **kwargs):
        """This functionnality does not exist in Comsol, use thicken instead"""
        raise NotImplementedError("sweep_along_path not implemented in Comsol mode")

    def thicken(self, layer, path, thickness):
        name = path.name
        wp = self._set_workplane(layer, name)
        thicken_name = self._new_transform_name(name)
        thicken = wp.geom().create(thicken_name, "Thicken2D")

        thicken.selection("input").set(self._penultimate_transform_name(name))
        thicken.set("totalthick", self._sympy_to_comsol_str(thickness)[0])

    def offset(self, name, layer, path, distance):
        wp = self._set_workplane(layer, path.name)
        offset = wp.geom().create(name, "Offset")
        offset.selection("input").set(self._last_transform_name(path.name))
        offset.set("distance", self._sympy_to_comsol_str(distance)[0])

        self.objects[offset.tag()] = offset

        return name

    def copy(self, entity):
        name = entity.name
        # wp = self._find_workplane(name)

        if name in self.deleted_entities:
            print(f"{name} not copied, must have been deleted by union")
        else:
            trans_name = gen_name(name)  ### self._new_transform_name(name)
            wp = self._set_workplane(entity.layer, trans_name)
            trans = wp.geom().create(trans_name, "Copy")
            trans.selection("input").set(self._last_transform_name(name))
            # self.model.java.param("inter_params").set(f"{trans_name}_x",
            #                                          self._sympy_to_comsol_str(vector[0]))
            # self.model.java.param("inter_params").set(f"{trans_name}_y",
            #                                          self._sympy_to_comsol_str(vector[1]))
            # trans.setIndex("displ", f"{trans_name}_x", 0)
            # trans.setIndex("displ", f"{trans_name}_y", 1)
            print(f"{name} copy ({trans_name})")
            return trans_name

    def wirebond(self, pos, ori, ymax, ymin, height="0.1mm", **kwargs):
        print("Wirebond should be drawn, not implemented yet")

    def assign_perfect_E(self, entities, name):
        if not isinstance(entities, list):
            entities = [entities]
        entity_names = [entity.name for entity in entities]

        for name in entity_names:
            self.main_wp.geom().feature(name).set("contributeto", "pec_sel")
            print("Perfect E assigned to {}".format(name))

    def assign_lumped_rlc(self, entity, r, l, c, start, end, name="RLC"):
        print("Lumped RLC should be assigned to {}, not implemented yet".format(entity.name))

    def rotate(self, entities, angle, center=None, *args, **kwargs):
        """Rotation occurs in the  plane of the object
        Only works with 2D geometries for now
        center must be a 2-elements tuple or list representing the position in the geometry's plane
        """

        if center is None:
            c = (0, 0)
        if not isinstance(entities, list):
            entities = [entities]
        names = [entity.name for entity in entities]

        for name in names:
            wp = self._find_workplane(name)

            if name in self.deleted_entities:
                print(f"{name} not translated, must have been deleted by union")
            else:
                rot_name = self._new_transform_name(name)
                rot = wp.geom().create(rot_name, "Rotate")
                rot.set("rot", angle)
                rot.setIndex("pos", self._sympy_to_comsol_str(c[0])[0], 0)
                rot.setIndex("pos", self._sympy_to_comsol_str(c[1])[0], 1)
                rot.selection("input").set(self._penultimate_transform_name(name))
                print(f"{name} rotated ({rot_name})")

    def translate(self, entities, vector):

        if not isinstance(entities, list):
            entities = [entities]
        names = [entity.name for entity in entities]

        if vector[2] != 0:
            print(
                "/!\\ WARNING: Translations outside of main workplane not implemented yet in Comsol mode, ignoring z component of the translation vector /!\\"
            )

        for name in names:
            # If object in dictionnary then
            # just add the translation to the initial object
            # if name in self.objects.keys():
            #    obj = self.objects[name]
            #    # obj.setIndex("pos", )
            #    print(f'{name} translation')

            # else:  # otherwise add a translation comsol object
            wp = self._find_workplane(name)

            if name in self.deleted_entities:
                print(f"{name} not translated, must have been deleted by union")
            else:
                # print("name=", name)
                trans_name = self._new_transform_name(name)
                print("trans_name=", trans_name)
                trans = wp.geom().create(trans_name, "Move")
                trans.selection("input").set(self._penultimate_transform_name(name))
                # self.model.java.param("inter_params").set(f"{trans_name}_x",
                #                                          self._sympy_to_comsol_str(vector[0]))
                # self.model.java.param("inter_params").set(f"{trans_name}_y",
                #                                          self._sympy_to_comsol_str(vector[1]))
                # trans.setIndex("displ", f"{trans_name}_x", 0)
                # trans.setIndex("displ", f"{trans_name}_y", 1)
                trans.set("displx", *self._sympy_to_comsol_str(vector[0]))
                trans.set("disply", *self._sympy_to_comsol_str(vector[1]))
                print(f"{name} translated ({trans_name})")

    def delete(self, entity, penultimate=False):
        if entity.name in self.deleted_entities:
            print("{} already deleted".format(entity.name))
        else:
            wp = self._find_workplane(entity.name)
            if penultimate:
                name_to_del = self._penultimate_transform_name(entity.name)
            else:
                name_to_del = self._last_transform_name(entity.name)
                self.deleted_entities.append(entity.name)

            del_name = "del_{}".format(name_to_del)
            delete = wp.geom().create(del_name, "Delete")
            delete.selection("input").init()
            delete.selection("input").set(name_to_del)
            print("{} deleted".format(entity.name))

    def unite(self, entities, keep_originals=False):
        if len(entities) == 0:
            return None

        if isinstance(entities[0], str):
            names = [
                self._last_transform_name(entity)
                for entity in entities
                if entity not in self.deleted_entities
            ]
        else:
            names = [
                self._last_transform_name(entity.name)
                for entity in entities
                if entity.name not in self.deleted_entities
            ]

        # We need to find in which workplane the object was created
        # We assume that the user does not want to unite objects from different layers (which would make no sense)
        print("unite : ", names)
        wp = self._find_workplane(entities[0].name)

        union_name = self._new_transform_name(names[0])
        union = wp.geom().create(union_name, "Union")
        union.set("intbnd", "off")
        if keep_originals:
            union.set("keep", "on")
        else:
            self.deleted_entities.extend([self._get_suffix(name) for name in names[1:]])
        union.selection("input").set(*names)
        return entities.pop(0)

    def subtract(self, blank_entities, tool_entities, keep_originals=False):
        """Tool entities are subtracted from blank entities"""
        blank_names = []
        for entity in blank_entities:
            blank_names.append(self._last_transform_name(entity.name))
        tool_names = []
        for entity in tool_entities:
            tool_names.append(self._last_transform_name(entity.name))

        if self._get_suffix(blank_names[0]) in self.main_wp_entities:
            wp = self.main_wp
        else:
            wp = self.mesh_port_wp

        for name in blank_names:
            diff_name = self._new_transform_name(name)
            print("diff_name : ", diff_name)
            diff = wp.geom().create(diff_name, "Difference")
            if keep_originals:
                diff.set("keep", "on")
            else:
                diff.set("keep", "off")
            diff.selection("input").set(name)
            diff.selection("input2").set(*tool_names)
            if not keep_originals:
                self.deleted_entities.extend(tool_names)

        for entity in blank_entities:
            self.delete(entity, penultimate=True)

    def rename(self, entity, new_name):
        wp = self._find_workplane(entity.name)
        wp.geom().feature(entity.name).tag(new_name)
        for i in range(1, self.transforms[entity.name] + 1):
            wp.geom().feature(f"t{i}_{entity.name}").tag(f"t{i}_{new_name}")
        self.transforms[new_name] = self.transforms.pop(entity.name)
        wp = self._set_workplane(entity.layer, new_name)
        self.main_wp_entities.remove(entity.name)

    def fillet(self, entity, radius, vertex_indices=None):
        """Filleting of a partial set on vertices not implemented yet
        All vertices are filleted with the same radius"""
        if vertex_indices is None:
            wp = self._find_workplane(entity.name)
            fillet_name = self._new_transform_name(entity.name)
            fillet = wp.geom().create(fillet_name, "Fillet")
            fillet.set("radius", *self._sympy_to_comsol_str(radius))
            ii = 1
            while True:
                try:
                    fillet.selection("point").add(self._penultimate_transform_name(entity.name), ii)
                    ii += 1
                    self.main_geom.run()
                except:
                    break
        else:
            pass

    def get_vertex_ids(self, entity):
        """
        sel_name = self._new_transform_name("get_vertex_ids")
        sel = self.main_wp.geom().create(sel_name, "ExplicitSelection")
        ids = []
        ii = 1
        while True:
            try:
                sel.selection("selection").add(self._last_transform_name(entity.name), ii)
                self.main_geom.run()
            except:
                break
            ids.append(ii)
            ii += 1
        """
        raise NotImplementedError("get_vertex_ids not implemented yet in Comsol mode")

    def get_vertices(self, entity):
        return []

    def assign_mesh_length(self, entities, length):
        pass

    def build(self):
        self.model.build()

    def add_mesh(self, name):
        import com  # # can be done once the JVM has been started by instantiating mph.Client...

        try:
            self.main_comp.mesh().create(name)
        except com.comsol.util.exceptions.FlException:
            print(f"Mesh {name} already exists")

    def add_physics(self, name, physics_type):
        import com  # # can be done once the JVM has been started by instantiating mph.Client...

        try:
            self.main_comp.physics().create(name, physics_type, "main_geom")
        except com.comsol.util.exceptions.FlException:
            print(f"Physics {name} already exists")

    def add_electrostatics_physics(self, name):
        self.add_physics(name, "Electrostatics")

    def add_electromagnetic_waves_physics(self, name):
        self.add_physics(name, "ElectromagneticWaves")

    #######################################
    #  Materials
    #######################################

    def add_electric_material(
        self, name, permeability="1", permittivity="1", conductivity="0", elements=[]
    ):
        material = self.main_comp.material().create(name)
        material.propertyGroup("def").set("relpermeability", list(permeability))
        material.propertyGroup("def").set("relpermittivity", list(permittivity))
        material.propertyGroup("def").set("electricconductivity", conductivity)

    #######################################
    #   Utils
    #######################################

    def _set_workplane(self, layer, name):
        """If given a layer, returns the associated workplane
        When creating an entity, add its name to the args to add it if necessary to the main_wp_entities list
        """

        if layer == layer_ids.MESH or layer == layer_ids.PORT:
            wp = self.mesh_port_wp
        elif layer == layer_ids.MASK:
            wp = self.mesh_port_wp
        else:
            wp = self.main_wp
            self.main_wp_entities.append(name)

        return wp

    @staticmethod
    def _sympy_to_comsol_str(*args):
        """Input argument: Sympy expressions. Output argument: string corresponding
        to the input expression where the power ** has been replaced with ^"""
        strings = ["(" + str(sympy_expr) + ")" for sympy_expr in args]
        return [
            s.replace("**", "^").replace("Abs", "abs").replace("Min", "min").replace("Max", "max")
            for s in strings
        ]

    @staticmethod
    def _make_3D(*args):
        """Adds a zero to 2D input lists representing 2D vectors. Does nothing
        to 3D vectors."""
        for vec in args:
            vec.append(0) if len(vec) == 2 else None
        return args

    def _make_positiv(self, pos, dim):
        if self.model.parameter(dim, evaluate=True) < 0:
            dim = "-(" + dim + ")"
            pos = pos + "+" + dim
        return pos, dim

    #######################################
    #   Transform names management
    #######################################

    def _new_transform_name(self, name):
        """Given a name, assigns a name to the next transform"""
        suffix = self._get_suffix(name)
        if suffix in self.transforms:
            self.transforms[suffix] += 1
        else:
            self.transforms[suffix] = 1
        new_name = "t{}_{}".format(self.transforms[suffix], suffix)

        return new_name

    def _last_transform_name(self, name):
        """Given a name, returns the last transform name of the corresponding entity"""
        suffix = self._get_suffix(name)
        if suffix in self.transforms:
            last_name = "t{}_{}".format(self.transforms[suffix], suffix)
        else:
            last_name = suffix
        return last_name

    def _penultimate_transform_name(self, name):
        """Given a name, returns the penultimate transform name of the corresponding entity"""
        suffix = self._get_suffix(name)
        if suffix in self.transforms:
            if self.transforms[suffix] > 1:
                pen_name = "t{}_{}".format(self.transforms[suffix] - 1, suffix)
            else:
                pen_name = suffix
        else:
            raise Exception("No penultimate name available")

        return pen_name

    def _get_suffix(self, name):
        """Given a name, finds the original name of the entity (without 'tN_')"""
        suffix = name
        if suffix[0] == "t" and suffix[1] in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]:
            ii = 2
            while True:
                if suffix[ii] == "_":
                    break
                else:
                    ii += 1
            suffix = suffix[ii + 1 :]
        return suffix

    def _find_workplane(self, name):
        # We need to find in which workplane the object was created
        return (
            self.main_wp if self._get_suffix(name) in self.main_wp_entities else self.mesh_port_wp
        )
