import json
from owlready2 import get_ontology, ThingClass
from rdflib.namespace import RDFS, XSD
from rdflib import Graph

# Load the Turtle file
g = Graph()
g.parse("model-20250313.ttl", format="turtle")

# Save it in RDF/XML format
g.serialize("model-20250313.owl", format="xml")

# Load the ontology
onto = get_ontology("model-20250313.owl").load()

# Function to expand a domain if it contains a union of multiple classes
def expand_domain(domain):
    expanded = set()
    for d in domain:
        if isinstance(d, list):  # If the domain is a union (Owlready2 stores unions as lists)
            expanded.update(d)  # Add all entities in the union
        else:
            expanded.add(d)  # Otherwise, add normally
    return expanded

# Function to categorize properties into direct and inherited, handling unionOf cases
def get_properties_by_category(cls):
    direct_properties = set()
    inherited_properties = {}

    # Iterate over all properties in the ontology
    for prop in onto.properties():
        expanded_domain = expand_domain(prop.domain)  # Expand domain if it's a union
        
        for ancestor in cls.ancestors():  # Check all ancestors, including itself
            if ancestor in expanded_domain:
                if cls == ancestor:  # Direct property
                    direct_properties.add(prop)
                else:  # Inherited property
                    inherited_properties[prop] = ancestor  # Store the class from which it's inherited

    return direct_properties, inherited_properties

# Function to get cardinality constraints for a property
def get_cardinality_constraints(prop):
    """ Extracts cardinality, minCardinality, and maxCardinality for a property. """
    return {
        "cardinality": getattr(prop, "cardinality", None),
        "min_cardinality": getattr(prop, "min_cardinality", None),
        "max_cardinality": getattr(prop, "max_cardinality", None)
    }

# Collect information in a dictionary
ontology_data = {"classes": []}

for cls in onto.classes():
    class_info = {
        "name": cls.name,
        "equivalent_classes": [eq.name for eq in cls.equivalent_to],  # Equivalent classes
        "direct_properties": [],
        "inherited_properties": []
    }
    
    # Get categorized properties
    direct_properties, inherited_properties = get_properties_by_category(cls)
    
    def process_property(prop):
        """ Extract relevant property details including cardinality. """
        property_info = {
            "name": prop.name,
            "domain": [d.name for d in expand_domain(prop.domain) if hasattr(d, "name")],  # Handle unionOf
            "range": [],
            "annotations": {
                "comment": prop.comment[0] if prop.comment else None,
                "label": prop.label[0] if prop.label else None,
            },
            "equivalent_properties": [eq.name for eq in prop.equivalent_to],  # Equivalent properties
            "cardinality": get_cardinality_constraints(prop)  # Add cardinality constraints
        }
        
        # Collect range information
        for r in prop.range:
            if hasattr(r, "name"):  # Ontology class
                property_info["range"].append(r.name)
            elif isinstance(r, type):  # Python-native type
                property_info["range"].append(r.__name__)
            else:  # Handle RDF datatypes like rdfs:float
                if r in {RDFS.Literal, XSD.float, XSD.string, XSD.integer}:
                    property_info["range"].append(r.qname)
                else:
                    property_info["range"].append(str(r))
        
        return property_info

    # Process direct properties
    class_info["direct_properties"] = [process_property(prop) for prop in direct_properties]

    # Process inherited properties, adding "inherited_from" field
    for prop, parent_class in inherited_properties.items():
        inherited_property_info = process_property(prop)
        inherited_property_info["inherited_from"] = parent_class.name  # Add superclass info
        class_info["inherited_properties"].append(inherited_property_info)

    ontology_data["classes"].append(class_info)

# Write the data to a JSON file
json_file_path = "ontology_data_with_cardinality.json"
with open(json_file_path, "w", encoding="utf-8") as json_file:
    json.dump(ontology_data, json_file, indent=4, ensure_ascii=False)

print(f"Ontology data with cardinality has been exported to {json_file_path}")