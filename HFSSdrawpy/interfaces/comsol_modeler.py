# -*- coding: utf-8 -*-
"""
Created on Tue Feb  9 16:04:58 2021

@author: Alexandre
"""


import ntpath
import __main__
import mph
from functools import wraps

from ..utils import parse_entry, val, Vector
from ..core.entity import gen_name

class ComsolModeler(object):

    def __init__(self):

        self.client = mph.Client(cores = 1, version = '5.6', port = 2036)
        self.pymodel = self.client.create(ntpath.basename(__main__.__file__))
        self.model = self.pymodel.java

        self.geometry_numbers = {}

        self.main_comp = self.model.component().create("main_comp", True)
        self.main_comp.geom().create("main_geom", 3)
        self.main_geom = self.model.component("main_comp").geom("main_geom")
        self.main_wp = self.main_geom.create("main_wp", "WorkPlane")
        self.main_comp.mesh().create("main_mesh")
        self.emw_physics = self.main_comp.physics().create("emw", "ElectromagneticWaves", "emw_geom")
        self.pec = self.emw_physics.create("pec", "PerfectElectricConductor", 2)
        self.pec_sel = self.main_wp.geom().selection().create("pec_sel", "CumulativeSelection")
        self.main_wp.set("selplaneshow", "on")
        self.pec.selection().named("main_geom_main_wp_pec_sel_bnd")

        self.model.param().group().create("inter_params")

        self.main_geom.run()

        input('COMSOL client created. Press enter when your GUI is ready.')



    def set_variable(self, name, value):

        def hfss_to_comsol(v):
            # Transforms '25pm' into '25[pm]'
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
        pass

    def set_coor_sys(self, *args, **kwargs):
        pass

    def assert_name(func):
        @wraps(func)
        def asserted_name(*args, **kwargs):
            name = func(*args, **kwargs)
            msg = 'Failed at generating a name for %s'%name
            assert name == kwargs['name'], msg
            return name
        return asserted_name

    @assert_name
    def rect(self, pos, size, **kwargs):

        if len(pos)==2:
            pos.append(0)
        if len(size)==2:
            size.append(0)
        pos = parse_entry(pos)
        size = parse_entry(size)
        index = size.index(0)
        if index>=0:
            axis = "xyz"[index]
            axes = "xyz"[0 : index : ] + "xyz"[index + 1 : :]
        w_idx, h_idx, axis_idx = {'x': (1, 2, 0),
                        'y': (0, 2, 1),
                        'z': (0, 1, 2)}[axis]

        if axis != 'z' or pos[2] != 0:
            raise Exception('Rectangles outside of main workplane not implemented yet in Comsol mode')

        rectangle_name = kwargs["name"]

        if self.model.param().evaluate(str(size[w_idx])) < 0:
            width = "-(" + str(size[w_idx]) + ")"
            pos_x = str(pos[w_idx]) + "+" + str(size[w_idx])
        else:
            width = str(size[w_idx])
            pos_x = str(pos[w_idx])

        if self.model.param().evaluate(str(size[h_idx])) < 0:
            height = "-(" + str(size[h_idx]) + ")"
            pos_y = str(pos[h_idx]) + "+" + str(size[h_idx])
        else:
            height = str(size[h_idx])
            pos_y = str(pos[h_idx])

        rect = self.main_wp.geom().create(rectangle_name, "Rectangle")
        self.model.param("inter_params").set("{}_width".format(rectangle_name), str(width))
        self.model.param("inter_params").set("{}_height".format(rectangle_name), str(height))
        self.model.param("inter_params").set("{}_pos_x".format(rectangle_name), str(pos_x))
        self.model.param("inter_params").set("{}_pos_y".format(rectangle_name), str(pos_y))
        rect.setIndex("size", "{}_width".format(rectangle_name), 0)
        rect.setIndex("size", "{}_height".format(rectangle_name), 1)
        rect.setIndex("pos", "{}_pos_x".format(rectangle_name), 0)
        rect.setIndex("pos", "{}_pos_y".format(rectangle_name), 1)

        #self.main_geom.run()

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
        for i in range(len(points)):
            if isinstance(points[i], tuple) and len(points[i]) == 2:
                points[i] += (0,)
            elif isinstance(points[i], list) and len(points[i]) == 2:
                points[i].append(0)

        points = parse_entry(points)
        polygon_name = kwargs["name"]

        pol = self.main_wp.geom().create(polygon_name, "Polygon")
        pol.set("source", "table")

        if closed:
            pol.set("type", "solid")
        else:
            pol.set("type", "open")

        for ii, point in enumerate(points):
            pol.setIndex("table", str(point[0]), ii, 0)
            pol.setIndex("table", str(point[1]), ii, 1)

        #self.main_geom.run()

        print('Polygon {} created'.format(polygon_name))

        return polygon_name


    def assign_perfect_E(self, entities, name):
        pass

        if not isinstance(entities, list):
            entities = [entities]
        entity_names = [entity.name for entity in entities]

        for name in entity_names:
            self.main_wp.geom().feature(name).set("contributeto", "pec_sel")
            print('Perfect E assigned to {}'.format(name))

        #self.main_geom.run()


    def rotate(self, entities, angle, center=None, *args, **kwargs):
        '''Rotation occurs in the  plane of the object
        Only works with 2D geometries for now
        center must be a 2-elements tuple or list representing the posotion in the geometry's plane'''
        if(center is None):
            center = (0, 0)
        if not isinstance(entities, list):
            entities = [entities]
        names = [entity.name for entity in entities]
        
        for name in names:
            try:
                rot_name = self.new_transform_name(name)
                rot = self.main_wp.geom().create(rot_name, "Rotate")
                rot.set("rot", angle)
                rot.setIndex("pos", str(center[0]), 0)
                rot.setIndex("pos", str(center[1]), 1)
                rot.selection("input").set(rot_name[1:])
                self.main_geom.run()
                print('{} rotated ({})'.format(name, rot_name))
            except:
                print('{} not translated, must have been suppressed by union'.format(name))


    def translate(self, entities, vector):
        if not isinstance(entities, list):
            entities = [entities]
        names = [entity.name for entity in entities]

        if vector[2] != 0:
            raise Exception('Translations outside of main workplane not implemented yet in Comsol mode')

        for name in names:
            try:
                trans_name = self.new_transform_name(name)
                trans = self.main_wp.geom().create(trans_name, "Move")
                trans.selection("input").set(trans_name[1:])
                self.model.param("inter_params").set("{}_x".format(trans_name), str(vector[0]))
                self.model.param("inter_params").set("{}_y".format(trans_name), str(vector[1]))
                trans.setIndex("displ", "{}_x".format(trans_name), 0)
                trans.setIndex("displ", "{}_y".format(trans_name), 1)
                self.main_geom.run()
                print('{} translated ({})'.format(name, trans_name))
            except:
                print('{} not translated, must have been suppressed by union'.format(name))

    def delete(self, entity):
        object_exists = False
        try:
            self.main_wp.geom().feature(new_name).tag()
            object_exists = True
        except:
            pass

        if object_exists:
            del_name = "del_{}".format(entity.name)
            delete = self.main_wp.geom().create(del_name, "Delete")
            delete.selection("input").set(entity.name)
            #self.main_geom.run()
            print('{} deleted'.format(entity.name))

    def unite(self, entities, keep_originals=False):
        names = [self.last_transform_name(entity.name) for entity in entities]
        union_name = self.new_transform_name(names[0])
        union = self.main_wp.geom().create(union_name, "Union")
        union.set("intbnd", "off")
        if keep_originals:
            union.set("keep", "on")
        union.selection("input").set(*names)
        #self.main_geom.run()
        return entities.pop(0)

    def subtract(self, blank_entities, tool_entities, keep_originals=False):
        blank_names = []
        for entity in blank_entities:
            blank_names.append(self.last_transform_name(entity.name))
        tool_names = []
        for entity in tool_entities:
            tool_names.append(self.last_transform_name(entity.name))

        for name in blank_names:
            diff_name = self.new_transform_name(name)
            diff = self.main_wp.geom().create(diff_name, "Difference")
            diff.selection("input").set(name)
            diff.selection("input2").set(*tool_names)


    def fillet(self, entity, radius, vertex_indices=None):
        if vertex_indices is not None:
            raise Exception("Vertices selection not implemented yet")

        fillet_name = "fillet_{}".format(entity.name)
        fillet = self.main_wp.geom().create(fillet_name, "Fillet")
        fillet.set("radius", str(radius))

        ii = 1
        while True:
            try:
                fillet.selection("point").add(self.last_transform_name(entity.name), ii)
                ii+=1
                self.main_geom.run()
            except:
                break
        print("Fillet applied to {}".format(entity.name))
        #self.main_geom.run()



    def new_transform_name(self, name):
        new_name = 't{}'.format(name)
        while True:
            try:
                new_name = 't{}'.format(self.main_wp.geom().feature(new_name).tag())
            except:
                break
        return new_name

    def last_transform_name(self, name):
        return self.new_transform_name(name)[1:]