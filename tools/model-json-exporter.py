import requests
import json
from rdflib import Graph, Namespace, BNode
from rdflib.namespace import RDF, RDFS, OWL, SKOS, DCTERMS

# Define namespaces
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")

def fetch_ttl_from_github(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        raise Exception(f"Failed to fetch TTL file. HTTP {response.status_code}")

def unroll_union(g, node):
    members = []
    current = g.value(node, OWL.unionOf)
    while current and current != RDF.nil:
        first = g.value(current, RDF.first)
        if first:
            members.append(first)
        current = g.value(current, RDF.rest)
    return members

# Recursively collect all superclasses
def get_superclasses(g, class_uri, visited=None):
    if visited is None:
        visited = set()
    if class_uri in visited:
        return visited
    visited.add(class_uri)
    for parent in g.objects(class_uri, RDFS.subClassOf):
        if isinstance(parent, BNode):
            continue
        visited.update(get_superclasses(g, parent, visited))
    return visited

def parse_model_ttl(ttl_content):
    g = Graph()
    g.parse(data=ttl_content, format="turtle")

    cardinality_predicates = {
        OWL.qualifiedCardinality: "owl:qualifiedCardinality",
        OWL.minQualifiedCardinality: "owl:minQualifiedCardinality",
        OWL.maxQualifiedCardinality: "owl:maxQualifiedCardinality",
        OWL.cardinality: "owl:cardinality",
        OWL.minCardinality: "owl:minCardinality",
        OWL.maxCardinality: "owl:maxCardinality"
    }

    cardinality_map = {}
    for restriction_node in g.subjects(RDF.type, OWL.Restriction):
        prop_uri = None
        cardinality_data = {}
        for p, o in g.predicate_objects(restriction_node):
            if p == OWL.onProperty:
                prop_uri = str(o)
            elif p in cardinality_predicates:
                pred = cardinality_predicates[p]
                try:
                    val = int(str(o))
                except ValueError:
                    val = str(o)
                cardinality_data[pred] = val
        if prop_uri and cardinality_data:
            for class_uri in g.subjects(RDFS.subClassOf, restriction_node):
                class_id = str(class_uri)
                if class_id not in cardinality_map:
                    cardinality_map[class_id] = {}
                if prop_uri not in cardinality_map[class_id]:
                    cardinality_map[class_id][prop_uri] = {}
                cardinality_map[class_id][prop_uri].update(cardinality_data)

    class_uris = set(g.subjects(RDF.type, OWL.Class))
    property_uris = set(g.subjects(RDF.type, OWL.ObjectProperty)).union(
        g.subjects(RDF.type, OWL.DatatypeProperty)
    )

    ontology_data = {"classes": []}
    class_index = {}

    # Build class index
    for class_uri in class_uris:
        if isinstance(class_uri, BNode):
            continue
        class_id = str(class_uri)
        label = next(g.objects(class_uri, RDFS.label), None)
        class_name = str(label) if label else class_id.split("/")[-1]

        # Collect equivalence and mapping relationships
        mapping_preds = [
            (OWL.equivalentClass, "owl:equivalentClass"),
            (SKOS.relatedMatch, "skos:relatedMatch"),
            (RDFS.seeAlso, "rdfs:seeAlso"),
            (DCTERMS.relation, "dct:relation"),
            (DCTERMS.conformsTo, "dct:conformsTo")
        ]

        equivalent_classes = []
        for pred, pred_label in mapping_preds:
            for obj in g.objects(class_uri, pred):
                if isinstance(obj, BNode):
                    continue
                equivalent_classes.append({
                    "predicate": pred_label,
                    "target": str(obj),
                    "type": "uri" if str(obj).startswith("http") else "literal"
                })

        class_info = {
            "name": class_name,
            "equivalent_classes": equivalent_classes,
            "direct_properties": [],
            "inherited_properties": []
        }
        ontology_data["classes"].append(class_info)
        class_index[class_uri] = class_info

    # Map properties to domain classes
    property_map = {}  # domain_uri -> list of property definitions
    for prop_uri in property_uris:
        prop_id = str(prop_uri)
        prop_label = next(g.objects(prop_uri, RDFS.label), None)
        prop_name = str(prop_label) if prop_label else prop_id.split("/")[-1]
        comment = next(g.objects(prop_uri, RDFS.comment), None)

        domains = set()
        for d in g.objects(prop_uri, RDFS.domain):
            if isinstance(d, BNode) and (d, OWL.unionOf, None) in g:
                domains.update(unroll_union(g, d))
            else:
                domains.add(d)

        ranges = set(g.objects(prop_uri, RDFS.range))

        prop_info = {
            "name": prop_name,
            "domain": [str(d).split("/")[-1] for d in domains],
            "range": [str(r).split("/")[-1] for r in ranges],
            "annotations": {
                "label": str(prop_label) if prop_label else None,
                "comment": str(comment) if comment else None
            },
            "equivalent_properties": [],
            "cardinality": {}
        }

        for domain_uri in domains:
            if domain_uri not in property_map:
                property_map[domain_uri] = []
            property_map[domain_uri].append((prop_info, prop_id))

    # Assign properties to each class
    for class_uri in class_index:
        class_info = class_index[class_uri]
        class_id = str(class_uri)

        # Direct properties
        if class_uri in property_map:
            for prop_info, prop_id in property_map[class_uri]:
                prop_copy = dict(prop_info)
                if class_id in cardinality_map and prop_id in cardinality_map[class_id]:
                    prop_copy["cardinality"] = cardinality_map[class_id][prop_id]
                class_info["direct_properties"].append(prop_copy)

        # Inherited properties
        for ancestor in get_superclasses(g, class_uri):
            if ancestor == class_uri or ancestor not in property_map:
                continue
            for prop_info, prop_id in property_map[ancestor]:
                prop_copy = dict(prop_info)
                prop_copy["inherited_from"] = str(ancestor).split("/")[-1]
                class_info["inherited_properties"].append(prop_copy)

    return ontology_data

def main():
    github_url = "https://raw.githubusercontent.com/aiondemand/metadata-schema/main/model/model.ttl"
    ttl_content = fetch_ttl_from_github(github_url)
    parsed_json = parse_model_ttl(ttl_content)

    output_path = "model-export.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(parsed_json, f, indent=4, ensure_ascii=False)

    print(f"✅ Ontology exported to {output_path}")

if __name__ == "__main__":
    main()

