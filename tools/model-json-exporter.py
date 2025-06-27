import requests
import json
from rdflib import Graph, Namespace
from rdflib.namespace import RDF, RDFS, OWL

# Define namespaces
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")

# === Fetch TTL from GitHub ===
def fetch_ttl_from_github(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        raise Exception(f"Failed to fetch the TTL file. HTTP {response.status_code}")

# === Parse TTL content and extract ontology info ===
def parse_model_ttl(ttl_content):
    g = Graph()
    g.parse(data=ttl_content, format="turtle")

    # Define relevant OWL cardinality predicates
    cardinality_predicates = {
        OWL.qualifiedCardinality: "owl:qualifiedCardinality",
        OWL.minQualifiedCardinality: "owl:minQualifiedCardinality",
        OWL.maxQualifiedCardinality: "owl:maxQualifiedCardinality",
        OWL.cardinality: "owl:cardinality",
        OWL.minCardinality: "owl:minCardinality",
        OWL.maxCardinality: "owl:maxCardinality"
    }

    # === Step 1: Extract cardinality restrictions ===
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
                class_name = str(class_uri)
                if class_name not in cardinality_map:
                    cardinality_map[class_name] = {}
                if prop_uri not in cardinality_map[class_name]:
                    cardinality_map[class_name][prop_uri] = {}
                cardinality_map[class_name][prop_uri].update(cardinality_data)

    # === Step 2: Extract classes and properties ===
    class_uris = set(g.subjects(RDF.type, OWL.Class))
    property_uris = set(g.subjects(RDF.type, OWL.ObjectProperty)).union(
        g.subjects(RDF.type, OWL.DatatypeProperty)
    )

    ontology_data = {"classes": []}

    for class_uri in class_uris:
        class_id = str(class_uri)
        class_name = class_id.split("/")[-1]

        class_info = {
            "name": class_name,
            "equivalent_classes": [],
            "direct_properties": [],
            "inherited_properties": []
        }

        # Get ancestors (simplified)
        direct_superclasses = set(g.objects(class_uri, RDFS.subClassOf))
        all_ancestors = direct_superclasses.union({class_uri})

        for prop_uri in property_uris:
            prop_id = str(prop_uri)
            prop_name = prop_id.split("/")[-1]

            domains = set(g.objects(prop_uri, RDFS.domain))
            ranges = set(g.objects(prop_uri, RDFS.range))

            is_direct = class_uri in domains
            is_inherited = any(ancestor in domains for ancestor in all_ancestors if ancestor != class_uri)

            prop_info = {
                "name": prop_name,
                "domain": [str(d).split("/")[-1] for d in domains],
                "range": [str(r).split("/")[-1] for r in ranges],
                "annotations": {
                    "label": None,
                    "comment": None
                },
                "equivalent_properties": [],
                "cardinality": {}
            }

            # Add label and comment if present
            label = next(g.objects(prop_uri, RDFS.label), None)
            comment = next(g.objects(prop_uri, RDFS.comment), None)
            if label:
                prop_info["annotations"]["label"] = str(label)
            if comment:
                prop_info["annotations"]["comment"] = str(comment)

            # Add cardinalities
            if class_id in cardinality_map and prop_id in cardinality_map[class_id]:
                prop_info["cardinality"] = cardinality_map[class_id][prop_id]

            # Assign to class
            if is_direct:
                class_info["direct_properties"].append(prop_info)
            elif is_inherited:
                prop_info["inherited_from"] = str(list(domains)[0]).split("/")[-1] if domains else None
                class_info["inherited_properties"].append(prop_info)

        ontology_data["classes"].append(class_info)

    return ontology_data

# === Main function ===
def main():
    github_url = "https://raw.githubusercontent.com/aiondemand/metadata-schema/main/model/model.ttl"
    ttl_content = fetch_ttl_from_github(github_url)
    parsed_json = parse_model_ttl(ttl_content)

    output_path = "ontology_data_with_cardinality.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(parsed_json, f, indent=4, ensure_ascii=False)

    print(f"✅ Ontology exported to {output_path}")

if __name__ == "__main__":
    main()


