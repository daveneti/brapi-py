"""brapi.entities — all BrAPI entity models."""

from .generated_allele_matrix import (
    AlleleMatrix, AlleleMatrixQuery, AlleleMatrixPagination, Pagination, DataMatrix,
)
from .generated_breeding_method import BreedingMethod, BreedingMethodQuery
from .generated_call import Call, CallQuery, GenotypeMetadata
from .generated_call_set import CallSet, CallSetQuery
from .generated_cross import Cross, CrossQuery, PollinationEvent, CrossAttribute
from .generated_crossing_project import CrossingProject, CrossingProjectQuery
from .generated_event import Event, EventQuery, EventParameter, EventDateRange
from .generated_genome_map import GenomeMap, GenomeMapQuery, LinkageGroup
from .generated_germplasm import (
    Donor, Germplasm, GermplasmMCPD, GermplasmQuery,
    StorageType, Synonym, TaxonId,
)
from .generated_germplasm_attribute import GermplasmAttribute, GermplasmAttributeQuery
from .generated_germplasm_attribute_value import (
    GermplasmAttributeValue, GermplasmAttributeValueQuery,
)
from .generated_image import Image, ImageQuery
from .generated_list import List, ListQuery
from .generated_location import Location, LocationQuery
from .generated_marker_position import MarkerPosition, MarkerPositionQuery
from .generated_method import Method, MethodQuery
from .generated_observation import Observation, ObservationQuery
from .generated_observation_unit import (
    ObservationUnit, ObservationUnitQuery, ObservationTreatment,
)
from .generated_observation_variable import ObservationVariable, ObservationVariableQuery
from .generated_ontology import Ontology, OntologyQuery
from .generated_pedigree_node import (
    PedigreeNode, PedigreeNodeQuery, GermplasmParent, GermplasmChild,
)
from .generated_person import Person, PersonQuery
from .generated_planned_cross import (
    PlannedCross, PlannedCrossQuery, PlannedCrossStatus, CrossStatus,
)
from .generated_plate import Plate, PlateQuery, SampleType, PlateFormat
from .generated_program import Program, ProgramQuery
from .generated_reference import Reference, ReferenceQuery, ReferenceBases
from .generated_reference_set import ReferenceSet, ReferenceSetQuery
from .generated_sample import Sample, SampleQuery
from .generated_scale import Scale, ScaleQuery
from .generated_season import Season, SeasonQuery
from .generated_seed_lot import SeedLot, SeedLotQuery, SeedLotTransaction, ContentMixture
from .generated_study import (
    Study, StudyQuery, DataLink, EnvironmentParameter, ExperimentalDesign,
    GrowthFacility, LastUpdate, ObservationUnitHierarchyLevel,
)
from .generated_trait import Trait, TraitQuery
from .generated_trial import Trial, TrialQuery, Publication, DatasetAuthorships
from .generated_variant import Variant, VariantQuery
from .generated_variant_set import (
    VariantSet, VariantSetQuery, Analysis, MetadataField, AvailableFormat,
)

# Hand-written germplasm module — overrides generated versions for shared names
from .germplasm import (
    Donor, ExternalReference, Germplasm, GermplasmOrigin,
    GermplasmQuery, StorageType, Synonym, TaxonId,
)

__all__ = [
    # allele matrix
    "AlleleMatrix", "AlleleMatrixQuery", "AlleleMatrixPagination", "Pagination", "DataMatrix",
    # breeding method
    "BreedingMethod", "BreedingMethodQuery",
    # call
    "Call", "CallQuery", "GenotypeMetadata",
    # call set
    "CallSet", "CallSetQuery",
    # cross
    "Cross", "CrossQuery", "PollinationEvent", "CrossAttribute",
    # crossing project
    "CrossingProject", "CrossingProjectQuery",
    # event
    "Event", "EventQuery", "EventParameter", "EventDateRange",
    # genome map
    "GenomeMap", "GenomeMapQuery", "LinkageGroup",
    # germplasm
    "Donor", "ExternalReference", "Germplasm", "GermplasmMCPD", "GermplasmOrigin",
    "GermplasmQuery", "StorageType", "Synonym", "TaxonId",
    # germplasm attribute
    "GermplasmAttribute", "GermplasmAttributeQuery",
    # germplasm attribute value
    "GermplasmAttributeValue", "GermplasmAttributeValueQuery",
    # image
    "Image", "ImageQuery",
    # list
    "List", "ListQuery",
    # location
    "Location", "LocationQuery",
    # marker position
    "MarkerPosition", "MarkerPositionQuery",
    # method
    "Method", "MethodQuery",
    # observation
    "Observation", "ObservationQuery",
    # observation unit
    "ObservationUnit", "ObservationUnitQuery", "ObservationTreatment",
    # observation variable
    "ObservationVariable", "ObservationVariableQuery",
    # ontology
    "Ontology", "OntologyQuery",
    # pedigree node
    "PedigreeNode", "PedigreeNodeQuery", "GermplasmParent", "GermplasmChild",
    # person
    "Person", "PersonQuery",
    # planned cross
    "PlannedCross", "PlannedCrossQuery", "PlannedCrossStatus", "CrossStatus",
    # plate
    "Plate", "PlateQuery", "SampleType", "PlateFormat",
    # program
    "Program", "ProgramQuery",
    # reference
    "Reference", "ReferenceQuery", "ReferenceBases",
    # reference set
    "ReferenceSet", "ReferenceSetQuery",
    # sample
    "Sample", "SampleQuery",
    # scale
    "Scale", "ScaleQuery",
    # season
    "Season", "SeasonQuery",
    # seed lot
    "SeedLot", "SeedLotQuery", "SeedLotTransaction", "ContentMixture",
    # study
    "Study", "StudyQuery", "DataLink", "EnvironmentParameter", "ExperimentalDesign",
    "GrowthFacility", "LastUpdate", "ObservationUnitHierarchyLevel",
    # trait
    "Trait", "TraitQuery",
    # trial
    "Trial", "TrialQuery", "Publication", "DatasetAuthorships",
    # variant
    "Variant", "VariantQuery",
    # variant set
    "VariantSet", "VariantSetQuery", "Analysis", "MetadataField", "AvailableFormat",
]

# ---------------------------------------------------------------------------
# Resolve forward references for models with cross-entity field types.
# Called here so that all entity classes are in scope (this module's globals)
# when Pydantic evaluates the deferred TYPE_CHECKING annotations.
# We override the name 'List' back to typing.List so that annotations like
# Optional[List[CallSet]] resolve correctly (the generated_list module
# exports a class also named List, which would shadow typing.List).
# ---------------------------------------------------------------------------
import typing as _typing
from pydantic import BaseModel as _BaseModel  # noqa: E402
import brapi.generated_common as _common

_rebuild_ns = {
    **{k: v for k, v in vars(_common).items() if not k.startswith('_')},
    **globals(),
    "List": _typing.List,  # restore typing.List, shadowed by generated_list.List
}

for _name in __all__:
    _obj = _rebuild_ns.get(_name)
    if isinstance(_obj, type) and issubclass(_obj, _BaseModel) and not _obj.__pydantic_complete__:
        _obj.model_rebuild(_types_namespace=_rebuild_ns)

del _name, _obj, _BaseModel, _rebuild_ns, _typing, _common
