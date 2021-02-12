import numpy as np
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

        self.model.component().create("main_comp", True);
        self.model.component("main_comp").geom().create("main_geom", 3);

        self.main_geom = self.model.component("main_comp").geom("main_geom")
        self.main_wp = self.main_geom.create("main_wp", "WorkPlane")

        start = input('COMSOL client created. Press enter when your GUI is ready.')



    def set_variable(self, name, value):
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
        rect.setIndex("size", width, 0)
        rect.setIndex("size", height, 1)
        rect.setIndex("pos", pos_x, 0)
        rect.setIndex("pos", pos_y, 1)
        self.main_geom.run()

        return rectangle_name

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
            rot_name = self.new_transform_name(name)
            rot = self.main_wp.geom().create(rot_name, "Rotate")
            rot.set("rot", angle)
            rot.setIndex("pos", str(center[0]), 0)
            rot.setIndex("pos", str(center[1]), 1)
            rot.selection("input").set(rot_name[1:])
            self.main_geom.run()



    def translate(self, entities, vector):
        if not isinstance(entities, list):
            entities = [entities]
        names = [entity.name for entity in entities]

        if vector[2] != 0:
            raise Exception('Translations outside of main workplane not implemented yet in Comsol mode')

        for name in names:
            trans_name = self.new_transform_name(name)

            trans = self.main_wp.geom().create(trans_name, "Move")
            trans.selection("input").set(trans_name[1:])
            trans.setIndex("displ", str(vector[0]), 0)
            trans.setIndex("displ", str(vector[1]), 1)
            self.main_geom.run()


    def new_transform_name(self, name):
        new_name = 't{}'.format(name)
        while True:
            try:
                new_name = 't{}'.format(self.main_wp.geom().feature(new_name).tag())
            except:
                break
        return new_name