from sqlalchemy import Column, String, Integer, Float, Numeric, Boolean
from sqlalchemy import ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.declarative import AbstractConcreteBase
from geoalchemy2 import Geometry
from emannotationschemas import get_schema, get_types
from emannotationschemas.base import NumericField, ReferenceAnnotation
from emannotationschemas.contact import Contact
import marshmallow as mm
Base = declarative_base()

annotation_models = {}

# TODO decide what to call this for real
root_model_name = "CellSegment"


class InvalidSchemaField(Exception):
    '''Exception raised if a schema can't be translated to a model'''


class TSBase(AbstractConcreteBase, Base):
    id = Column(Integer, primary_key=True)
    # @declared_attr
    # def table_name(cls):
    #     return Column(String(50), ForeignKey('locations.table_name'))


def make_all_models(datasets, include_pychunkedgraph=False):
    model_dict = {}
    types = get_types()
    for dataset in datasets:
        model_dict[dataset] = {}
        for type_ in types:
            model_dict[dataset][type_] = make_annotation_model(dataset, type_)
        if include_pychunkedgraph:
            cell_segment_model = make_cell_segment_model(dataset)
            model_dict[dataset][root_model_name.lower()] = cell_segment_model
            contact_model = make_annotation_model_from_schema(dataset,
                                                              'contact',
                                                              Contact)
            model_dict[dataset]['contact'] = contact_model
    return model_dict


field_column_map = {
    NumericField: Numeric,
    mm.fields.Int: Integer,
    mm.fields.Integer: Integer,
    mm.fields.Float: Float,
    mm.fields.Str: String,
    mm.fields.String: String,
    mm.fields.Bool: Boolean,
    mm.fields.Boolean: Boolean
}


def add_column(attrd, k, field, dataset):
    field_type = type(field)
    do_index = field.metadata.get('index', False)
    if field_type in field_column_map:
        attrd[k] = Column(field_column_map[field_type], index=do_index)
    else:
        if isinstance(field, mm.fields.Nested):
            if field.many:
                raise InvalidSchemaField("Nested(many=True) not supported")
            for sub_k, sub_field in field.nested._declared_fields.items():
                do_sub_index = sub_field.metadata.get('index', False)
                postgis_geom = sub_field.metadata.get('postgis_geometry',
                                                      None)
                if postgis_geom:
                    attrd[k + "_" + sub_k] = Column(Geometry(postgis_geom,
                                                             dimension=3))
                else:
                    dyn_args = [field_column_map[type(sub_field)]]
                    if sub_k == 'root_id':
                        fk = dataset + "_" + root_model_name + ".id"
                        dyn_args.append(ForeignKey(fk))
                    attrd[k + "_" +
                          sub_k] = Column(*dyn_args,
                                          index=do_sub_index)
        else:
            raise InvalidSchemaField(
                "field type {} not supported".format(field_type))
    return attrd


def make_cell_segment_model(dataset):
    attr_dict = {
        '__tablename__': dataset + '_' + root_model_name
    }
    model_name = dataset.capitalize() + root_model_name
    if model_name not in annotation_models:
        annotation_models[model_name] = type(model_name, (TSBase,), attr_dict)
    return annotation_models[model_name]


def make_annotation_model_from_schema(dataset, annotation_type, Schema):

    model_name = dataset.capitalize() + annotation_type.capitalize()

    if model_name not in annotation_models:
        attrd = {
            '__tablename__': dataset + '_' + annotation_type,
            '__mapper_args__': {
                'polymorphic_identity': dataset,
                'concrete': True
            }
        }
        for k, field in Schema._declared_fields.items():
            if (not field.metadata.get('drop_column', False)):
                attrd = add_column(attrd, k, field, dataset)
        if issubclass(Schema, ReferenceAnnotation):
            target_field = Schema._declared_fields['target_id']
            reference_type = target_field.metadata['reference_type']
            attrd['target_id'] = Column(Integer, ForeignKey(
                dataset + '_' + reference_type + '.id'))
        annotation_models[model_name] = type(model_name, (TSBase,), attrd)

    return annotation_models[model_name]


def make_annotation_model(dataset, annotation_type):
    Schema = get_schema(annotation_type)
    return make_annotation_model_from_schema(dataset, annotation_type, Schema)
