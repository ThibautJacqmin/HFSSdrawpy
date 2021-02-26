# -*- coding: utf-8 -*-
"""
Created on Tue Feb  9 16:04:58 2021

@author: Alexandre

Next things to do :
    - Assign lumped RLC
    - Refine mesh (assign mesh length)
    - Draw wirebond
"""


import ntpath
import __main__
import mph
import drawpylib.parameters as layer_ids
from functools import wraps

from ..utils import parse_entry, val, Vector
from ..core.entity import gen_name

class ComsolModeler(object):

    def __init__(self):
        '''Comsol Modeler opens a Comsol client with mph, you need to have a Comsol server
        of the right version (5.6 by defalut) listening on port 2036
        To see the results in the GUI, open a Comsol client and import the running model'''

        #mph is only used to create a client, then the Python-Java bridge JPype is used throughout the code
        self.version = '5.6'
        self.client = mph.Client(cores = 1, version = self.version, port = 2036)
        self.pymodel = self.client.create(ntpath.basename(__main__.__file__))
        self.model = self.pymodel.java

        self.deleted_entities = []

        # dict containing the number of transforms having been applied to a given entity
        # every new transformation is named tN_name where name is the actual entity name and N-1 the number of transforms
        # it has already experienced
        # New trasnforms should always be applied to self._last_transfrom_name(name)
        self.transforms = {}

        self.main_comp = self.model.component().create("main_comp", True)
        self.main_comp.geom().create("main_geom", 3)
        self.main_geom = self.model.component("main_comp").geom("main_geom")

        #two workplanes are created : one for all physical components (main_wp) and one for MESH and PORT layers
        self.main_wp = self.main_geom.create("main_wp", "WorkPlane")
        self.main_wp_entities = []
        self.mesh_port_wp = self.main_geom.create("mesh_port_wp", "WorkPlane")
        self.main_comp.mesh().create("main_mesh")

        #PEC assignment is tricky, we create a selection "pec_sel" in the main wp,
        #and make it visible from the physics by setting "selplaneshow" to "on"
        #the boundaries belonging to pec_sel are then the input of a PEC in the physics
        self.emw_physics = self.main_comp.physics().create("emw", "ElectromagneticWaves", "emw_geom")
        self.pec = self.emw_physics.create("pec", "PerfectElectricConductor", 2)
        self.pec_sel = self.main_wp.geom().selection().create("pec_sel", "CumulativeSelection")
        self.main_wp.set("selplaneshow", "on")
        self.pec.selection().named("main_geom_main_wp_pec_sel_bnd")

        #Comsol fails to read to long expressions, so we create intermediray parameters in a second table
        self.inter_params = self.model.param().group().create("inter_params")

        self.main_geom.run()

        input('COMSOL client created. Press enter when your GUI is ready.')


    def set_variable(self, name, value):
        '''The parameter is added in the main param table, which is the only one that should be used in the GUI'''

        def hfss_to_comsol(v):
            '''Transforms '25um' into '25[um]'''
            numerics = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '.', 'e', '+', '-']
            for i, c in enumerate(str(v)):
                if c not in numerics:
                    break
            return '{}[{}]'.format(v[:i], v[i:])

        if isinstance(value, str):
            self.model.param().set(name, str(hfss_to_comsol(value)))
        else:
            self.model.param().set(name, str(value))

    def create_coor_sys(self, *args, **kwargs):
        '''Only uselful in hfss'''
        pass

    def set_coor_sys(self, *args, **kwargs):
        '''Only uselful in hfss'''
        pass

    def assert_name(func):
        '''Decorator checking the coherence of the entity's name'''
        @wraps(func)
        def asserted_name(*args, **kwargs):
            name = func(*args, **kwargs)
            msg = 'Failed at generating a name for %s'%name
            assert name == kwargs['name'], msg
            return name
        return asserted_name


    @assert_name
    def box(self, pos, size, **kwargs):
        ''' /!\ The rotate and translate methods are not implemented for 3D objects in Comsol yet! /!\ '''

        if len(pos)==2:
            pos.append(0)
        if len(size)==2:
            size.append(0)
        pos = parse_entry(pos)
        size = parse_entry(size)
        name = kwargs["name"]

        #Comsol does not support negative sizes, so this is dealt with here
        if self.model.param().evaluate(self._comsol_str(size[0])) < 0:
            size_0 = "-(" + self._comsol_str(size[0]) + ")"
            pos_0 = self._comsol_str(pos[0]) + "+" + self._comsol_str(size[0])
        else:
            size_0 = self._comsol_str(size[0])
            pos_0 = self._comsol_str(pos[0])

        if self.model.param().evaluate(self._comsol_str(size[1])) < 0:
            size_1 = "-(" + self._comsol_str(size[1]) + ")"
            pos_1 = self._comsol_str(pos[1]) + "+" + self._comsol_str(size[1])
        else:
            size_1 = self._comsol_str(size[1])
            pos_1 = self._comsol_str(pos[1])

        if self.model.param().evaluate(self._comsol_str(size[2])) < 0:
            size_2 = "-(" + self._comsol_str(size[2]) + ")"
            pos_2 = self._comsol_str(pos[2]) + "+" + self._comsol_str(size[2])
        else:
            size_2 = self._comsol_str(size[2])
            pos_2 = self._comsol_str(pos[2])

        box = self.main_geom.create(name, "Block");
        box.setIndex("size", size_0, 0)
        box.setIndex("size", size_1, 1)
        box.setIndex("size", size_2, 2)

        box = self.main_geom.create(name, "Block");
        box.setIndex("pos", pos_0, 0)
        box.setIndex("pos", pos_1, 1)
        box.setIndex("pos", pos_2, 2)

        return name

    @assert_name
    def box_center(self, pos, size, **kwargs):
        pos = parse_entry(pos)
        size = parse_entry(size)
        corner_pos = [val(p) - val(s)/2 for p, s in zip(pos, size)]
        return self.box(corner_pos, size, **kwargs)


    @assert_name
    def rect(self, pos, size, **kwargs):

        rectangle_name = kwargs["name"]
        layer = kwargs["layer"]

        if len(pos)==2:
            pos.append(0)
        if len(size)==2:
            size.append(0)
        pos = parse_entry(pos)
        size = parse_entry(size)

        # Comsol does not support negative sizes, so this is dealt with here
        if self.model.param().evaluate(self._comsol_str(size[0])) < 0:
            width = "-(" + self._comsol_str(size[0]) + ")"
            pos_x = self._comsol_str(pos[0]) + "+" + self._comsol_str(size[0])
        else:
            width = self._comsol_str(size[0])
            pos_x = self._comsol_str(pos[0])

        if self.model.param().evaluate(self._comsol_str(size[1])) < 0:
            height = "-(" + self._comsol_str(size[1]) + ")"
            pos_y = self._comsol_str(pos[1]) + "+" + self._comsol_str(size[1])
        else:
            height = self._comsol_str(size[1])
            pos_y = self._comsol_str(pos[1])

        #If the rectangle is in the MESH or PORT layer, it should be added to the specific workplane
        wp = self._set_workplane(layer, rectangle_name)

        rect = wp.geom().create(rectangle_name, "Rectangle")
        self.inter_params.set("{}_width".format(rectangle_name), self._comsol_str(width))
        self.inter_params.set("{}_height".format(rectangle_name), self._comsol_str(height))
        self.inter_params.set("{}_pos_x".format(rectangle_name), self._comsol_str(pos_x))
        self.inter_params.set("{}_pos_y".format(rectangle_name), self._comsol_str(pos_y))
        rect.setIndex("size", "{}_width".format(rectangle_name), 0)
        rect.setIndex("size", "{}_height".format(rectangle_name), 1)
        rect.setIndex("pos", "{}_pos_x".format(rectangle_name), 0)
        rect.setIndex("pos", "{}_pos_y".format(rectangle_name), 1)

        print('Rectangle {} created'.format(rectangle_name))

        return rectangle_name

    @assert_name
    def rect_center(self, pos, size, **kwargs):
        pos = parse_entry(pos)
        size = parse_entry(size)
        corner_pos = [val(p) - val(s)/2 for p, s in zip(pos, size)]
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

        for ii, point in enumerate(points):
            pol.setIndex("table", self._comsol_str(point[0]), ii, 0)
            pol.setIndex("table", self._comsol_str(point[1]), ii, 1)

        print('Polygon {} created'.format(polygon_name))

        return polygon_name

    def sweep_along_path(self, points, port_ori, port_pos, port_width, fillet_radius, path_name, **kwargs):
        '''This functionnality does not exist in Comsol, so the trick is the following:
            - Create a new 3D geometry
            - Create the line to be swept along in a xy workplane (polygon + fillet)
            - Create a square of size "width" in an orthogonal workplane, in the right orientation and at the right position
            - Sweep the square along the line to make a 3D object
            - Import this 3D object in the main geometry
            - Take the intersection (cross section) of this object in the main workplane
            - Delete the 3D object'''

        layer = kwargs["layer"]

        comp_name = self._new_transform_name("path_generator")
        geom_name = self._new_transform_name("line_geom")
        wp_line_name = self._new_transform_name("wp_line")
        line_name = self._new_transform_name("line")
        wp_sq_name = self._new_transform_name("wp_sq")
        import_name = self._new_transform_name("import")
        cross_section_name = path_name
        sweep_name = self._new_transform_name("sweep")
        delete_name = self._new_transform_name("del")

        #We first create the geometry and the line's wp
        comp = self.model.component().create(comp_name, True)
        geom = comp.geom().create(geom_name, 3)
        wp_line = geom.create(wp_line_name, "WorkPlane")

        #Then the line is drawn in this wp
        line = wp_line.geom().create(line_name, "Polygon")
        line.set("source", "table")
        line.set("type", "open")
        nb_edges = 2 * len(points) - 3 #number of edges after filleting an open polygon

        for ii, point in enumerate(points):
            self.inter_params.set("{}_point_{}_x".format(line_name, str(ii)), self._comsol_str(point[0]))
            self.inter_params.set("{}_point_{}_y".format(line_name, str(ii)), self._comsol_str(point[1]))
            line.setIndex("table", "{}_point_{}_x".format(line_name, str(ii)), ii, 0)
            line.setIndex("table", "{}_point_{}_y".format(line_name, str(ii)), ii, 1)

        geom.run()

        #The line is now being filleted
        fillet_name = self._new_transform_name(line_name)
        fillet = wp_line.geom().create(fillet_name, "Fillet")
        fillet.set("radius", self._comsol_str(fillet_radius))
        ii = 1
        while True:
            try:
                fillet.selection("point").add(line_name, ii)
                ii += 1
                geom.run()
            except:
                break

        #The orthogonal workplane is created, oriented and placed here
        wp_sq = geom.create(wp_sq_name, "WorkPlane")

        geom.run()

        wp_sq.set("planetype", "normalvector")
        self.inter_params.set("{}_port_ori_x".format(line_name), self._comsol_str(port_ori[0]))
        self.inter_params.set("{}_port_ori_y".format(line_name), self._comsol_str(port_ori[1]))
        wp_sq.setIndex("normalvector", "{}_port_ori_x".format(line_name), 0)
        wp_sq.setIndex("normalvector", "{}_port_ori_y".format(line_name), 1)
        wp_sq.setIndex("normalvector", "0", 2)

        geom.run()

        self.inter_params.set("{}_port_pos_x".format(line_name), self._comsol_str(port_pos[0]))
        self.inter_params.set("{}_port_pos_y".format(line_name), self._comsol_str(port_pos[1]))
        wp_sq.setIndex("normalcoord", "{}_port_pos_x".format(line_name), 0)
        wp_sq.setIndex("normalcoord", "{}_port_pos_y".format(line_name), 1)
        wp_sq.setIndex("normalcoord", "0", 2)

        geom.run()

        #A square is created at the origin
        sq = wp_sq.geom().create("sq", "Square")
        sq.set("base", "center")
        sq.set("size", self._comsol_str(port_width))

        geom.run()

        #The square is swept along the line
        sweep = geom.create(sweep_name, "Sweep")
        sweep.set("smooth", "off")
        sweep.set("keep", "off")
        sweep.selection("face").set(wp_sq_name, 1)
        for edge_idx in range(1, nb_edges + 1):
            sweep.selection("edge").add(wp_line_name, edge_idx)

        geom.run()

        #The resulting 3D object is imported in the main geometry
        _import = self.main_geom.create(import_name, "Import")
        _import.set("type", "sequence")
        _import.set("sequence", geom_name)
        _import.importData()
        self.main_geom.feature().move(import_name, 0)

        wp = self._set_workplane(layer, path_name)

        #The (2-dimensional) instersection is taken
        cross_section = wp.geom().create(cross_section_name, "CrossSection")
        cross_section.set("intersect", "selected")
        cross_section.selection("input").set(import_name)

        #We can now delete the 3D geometry
        delete = self.main_geom.create(delete_name, "Delete")
        delete.selection("input").init(3)
        delete.selection("input").set(import_name, 1)
        # /!\ We place the Delete action AFTER the main workplane in Comsol's chonology,
        #otherwise the intersection cannot be taken
        self.main_geom.feature().move(delete_name, self.transforms["import"]+1)

        return path_name


    def wirebond(self, pos, ori, ymax, ymin, height='0.1mm', **kwargs):
        print("Wirebond should be drawn, not implemented yet")


    def assign_perfect_E(self, entities, name):
        if not isinstance(entities, list):
            entities = [entities]
        entity_names = [entity.name for entity in entities]

        for name in entity_names:
            self.main_wp.geom().feature(name).set("contributeto", "pec_sel")
            print('Perfect E assigned to {}'.format(name))


    def assign_lumped_rlc(self, entity, r, l, c, start, end, name="RLC"):
        print("Lumped RLC should be assigned to {}, not implemented yet".format(entity.name))


    def rotate(self, entities, angle, center=None, *args, **kwargs):
        '''Rotation occurs in the  plane of the object
        Only works with 2D geometries for now
        center must be a 2-elements tuple or list representing the position in the geometry's plane'''

        if(center is None):
            center = (0, 0)
        if not isinstance(entities, list):
            entities = [entities]
        names = [entity.name for entity in entities]

        for name in names:
            # We need to find in which workplane the object was created
            if self._get_suffix(name) in self.main_wp_entities:
                wp = self.main_wp
            else:
                wp = self.mesh_port_wp

            if name in self.deleted_entities:
                print('{} not translated, must have been deleted by union'.format(name))
            else:
                rot_name = self._new_transform_name(name)
                rot = wp.geom().create(rot_name, "Rotate")
                rot.set("rot", angle)
                rot.setIndex("pos", self._comsol_str(center[0]), 0)
                rot.setIndex("pos", self._comsol_str(center[1]), 1)
                rot.selection("input").set(self._penultimate_transform_name(name))
                print('{} rotated ({})'.format(name, rot_name))


    def translate(self, entities, vector):

        if not isinstance(entities, list):
            entities = [entities]
        names = [entity.name for entity in entities]

        if vector[2] != 0:
            raise Exception('Translations outside of main workplane not implemented yet in Comsol mode')

        for name in names:
            # We need to find in which workplane the object was created
            if self._get_suffix(name) in self.main_wp_entities:
                wp = self.main_wp
            else:
                wp = self.mesh_port_wp

            if name in self.deleted_entities:
                print('{} not translated, must have been deleted by union'.format(name))
            else:
                trans_name = self._new_transform_name(name)
                trans = wp.geom().create(trans_name, "Move")
                trans.selection("input").set(self._penultimate_transform_name(name))
                self.model.param("inter_params").set("{}_x".format(trans_name), self._comsol_str(vector[0]))
                self.model.param("inter_params").set("{}_y".format(trans_name), self._comsol_str(vector[1]))
                trans.setIndex("displ", "{}_x".format(trans_name), 0)
                trans.setIndex("displ", "{}_y".format(trans_name), 1)
                print('{} translated ({})'.format(name, trans_name))


    def delete(self, entity):
        if entity.name in self.deleted_entities:
            print("{} already deleted".format(entity.name))
        else:
            # We need to find in which workplane the object was created
            if self._get_suffix(entity.name) in self.main_wp_entities:
                wp = self.main_wp
            else:
                wp = self.mesh_port_wp

            del_name = "del_{}".format(entity.name)
            delete = wp.geom().create(del_name, "Delete")
            delete.selection("input").init()
            delete.selection("input").set(self._last_transform_name(entity.name))
            self.deleted_entities.append(entity.name)
            print('{} deleted'.format(entity.name))

    def unite(self, entities, keep_originals=False):
        if len(entities) == 0:
            return None

        if isinstance(entities[0], str):
            names = [self._last_transform_name(entity) for entity in entities if entity not in self.deleted_entities]
        else:
            names = [self._last_transform_name(entity.name) for entity in entities if entity.name not in self.deleted_entities]

        # We need to find in which workplane the object was created
        # We assume that the user does not want to unite objects from different layers (which would make no sense)
        if self._get_suffix(entities[0].name) in self.main_wp_entities:
            wp = self.main_wp
        else:
            wp = self.mesh_port_wp

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
        '''Tool entities are subtracted from blank entities
        '''
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
            diff = wp.geom().create(diff_name, "Difference")
            if keep_originals:
                diff.set("keep", "on")
            diff.selection("input").set(name)
            diff.selection("input2").set(*tool_names)
            if not keep_originals:
                self.deleted_entities.extend(tool_names)


    def fillet(self, entity, radius, vertex_indices=None):
        '''Filleting of a partial set on vertices not implemented yet
            All vertices are filleted with the same radius'''
        if vertex_indices is None:
            if self._get_suffix(entity.name) in self.main_wp_entities:
                wp = self.main_wp
            else:
                wp = self.mesh_port_wp
            fillet_name = self._new_transform_name(entity.name)
            fillet = wp.geom().create(fillet_name, "Fillet")
            fillet.set("radius", self._comsol_str(radius))
            ii = 1
            while True:
                try:
                    fillet.selection("point").add(self._penultimate_transform_name(entity.name), ii)
                    ii+=1
                    self.main_geom.run()
                except:
                    break
        else:
            pass


    def get_vertex_ids(self, entity):
        '''
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
        '''
        pass

    def assign_mesh_length(self, entities, length):
        pass

#######################################
#   Utils
#######################################


    def _set_workplane(self, layer, name):
        '''If given a layer, returns the associated workplane
        When creating an entity, add its name to the args to add it if necessary to the main_wp_entities list'''

        if layer == layer_ids.MESH or layer == layer_ids.PORT:
            wp = self.mesh_port_wp
        else:
            wp = self.main_wp
            self.main_wp_entities.append(name)

        return wp


    def _comsol_str(self, sympy_expr):
        string = str(sympy_expr)
        return string.replace("**", "^")


#######################################
#   Transform names management
#######################################


    def _new_transform_name(self, name):
        '''Given a name, assigns a name to the next transform'''
        suffix = self._get_suffix(name)
        if suffix in self.transforms:
            self.transforms[suffix] += 1
        else:
            self.transforms[suffix] = 1
        new_name = "t{}_{}".format(self.transforms[suffix], suffix)

        return new_name

    def _last_transform_name(self, name):
        '''Given a name, returns the last transform name of the corresponding entity'''
        suffix = self._get_suffix(name)
        if suffix in self.transforms:
            last_name = "t{}_{}".format(self.transforms[suffix], suffix)
        else:
            last_name = suffix
        return last_name

    def _penultimate_transform_name(self, name):
        '''Given a name, returns the penultimate transform name of the corresponding entity'''
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
        '''Given a name, finds the original name of the entity (without 'tN_') '''
        suffix = name
        if suffix[0] == 't' and suffix[1] in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
            ii = 2
            while True:
                if suffix[ii] == '_':
                    break
                else:
                    ii += 1
            suffix = suffix[ii + 1:]
        return suffix