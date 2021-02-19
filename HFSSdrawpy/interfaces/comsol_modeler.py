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

        self.suppressed_entities = []
        self.transforms = {} #dict containing the number of transforms having been applied to a given entity

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

        print('Polygon {} created'.format(polygon_name))

        return polygon_name


    def assign_perfect_E(self, entities, name):
        if not isinstance(entities, list):
            entities = [entities]
        entity_names = [entity.name for entity in entities]

        for name in entity_names:
            self.main_wp.geom().feature(name).set("contributeto", "pec_sel")
            print('Perfect E assigned to {}'.format(name))

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
            if name in self.suppressed_entities:
                print('{} not translated, must have been suppressed by union'.format(name))
            else:
                #t1 = time.perf_counter()
                rot_name = self.new_transform_name(name)
                #t2 = time.perf_counter()
                #print("New rot name generation time : ", t2 - t1)
                rot = self.main_wp.geom().create(rot_name, "Rotate")
                rot.set("rot", angle)
                rot.setIndex("pos", str(center[0]), 0)
                rot.setIndex("pos", str(center[1]), 1)
                rot.selection("input").set(self.penultimate_transform_name(name))
                print('{} rotated ({})'.format(name, rot_name))


    def translate(self, entities, vector):
        if not isinstance(entities, list):
            entities = [entities]
        names = [entity.name for entity in entities]

        if vector[2] != 0:
            raise Exception('Translations outside of main workplane not implemented yet in Comsol mode')

        for name in names:
            if name in self.suppressed_entities:
                print('{} not translated, must have been suppressed by union'.format(name))
            else:
                trans_name = self.new_transform_name(name)
                trans = self.main_wp.geom().create(trans_name, "Move")
                trans.selection("input").set(self.penultimate_transform_name(name))
                self.model.param("inter_params").set("{}_x".format(trans_name), str(vector[0]))
                self.model.param("inter_params").set("{}_y".format(trans_name), str(vector[1]))
                trans.setIndex("displ", "{}_x".format(trans_name), 0)
                trans.setIndex("displ", "{}_y".format(trans_name), 1)
                print('{} translated ({})'.format(name, trans_name))


    def delete(self, entity):
        if entity.name in self.suppressed_entities:
            print("{} not deleted, must have been suppressed by union".format(entity.name))
        else:
            del_name = "del_{}".format(entity.name)
            delete = self.main_wp.geom().create(del_name, "Delete")
            delete.selection("input").set(entity.name)
            print('{} deleted'.format(entity.name))

    def unite(self, entities, keep_originals=False):
        names = [self.last_transform_name(entity.name) for entity in entities]
        union_name = self.new_transform_name(names[0])
        union = self.main_wp.geom().create(union_name, "Union")
        union.set("intbnd", "off")
        if keep_originals:
            union.set("keep", "on")
        else:
            self.suppressed_entities.extend(names[1:])
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
            #diff.set("keep", "on")
            diff.selection("input").set(name)
            diff.selection("input2").set(*tool_names)
            self.suppressed_entities.extend(tool_names) #temporary solution, I don't understand how subtract works exactly in hfss


    def fillet(self, entity, radius, vertex_indices=None):

        fillet_name = self.new_transform_name(entity.name)
        fillet = self.main_wp.geom().create(fillet_name, "Fillet")
        fillet.set("radius", str(radius))

        if vertex_indices is None:
            ii = 1
            while True:
                try:
                    fillet.selection("point").add(self.penultimate_transform_name(entity.name), ii)
                    ii+=1
                    self.main_geom.run()
                except:
                    break
        else:
            pass


    def get_vertex_ids(self, entity):
        sel_name = self.new_transform_name("get_vertex_ids")
        sel = self.main_wp.geom().create(sel_name, "ExplicitSelection")
        ids = []
        ii = 1
        while True:
            try:
                sel.selection("selection").add(self.last_transform_name(entity.name), ii)
                self.main_geom.run()
            except:
                break
            ids.append(ii)
            ii += 1


        return ids

    def assign_mesh_length(self, entities, length):
        pass

#######################################
    # Transform names management
#######################################


    def new_transform_name(self, name):
        suffix = self.get_suffix(name)
        if suffix in self.transforms:
            self.transforms[suffix] += 1
        else:
            self.transforms[suffix] = 1
        new_name = "t{}_{}".format(self.transforms[suffix], suffix)

        return new_name

    def last_transform_name(self, name):
        suffix = self.get_suffix(name)
        if suffix in self.transforms:
            last_name = "t{}_{}".format(self.transforms[suffix], suffix)
        else:
            last_name = suffix
        return last_name

    def penultimate_transform_name(self, name):
        suffix = self.get_suffix(name)
        if suffix in self.transforms:
            if self.transforms[suffix] > 1:
                pen_name = "t{}_{}".format(self.transforms[suffix] - 1, suffix)
            else:
                pen_name = suffix
        else:
            raise Exception("No penultimate name available")

        return pen_name

    def get_suffix(self, name):
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