import requests
from rdflib import Graph, Namespace
import json
import logging

# Setup logging to debug the rdflib parsing process
logging.basicConfig(level=logging.INFO)

# Define namespaces
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

def fetch_ttl_from_github(url):
    """Fetches TTL content from a GitHub URL."""
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        raise Exception(f"Failed to fetch the TTL file. HTTP Status Code: {response.status_code}")

def parse_ttl_to_json(ttl_content):
    """Parses a TTL content into a JSON structure with hierarchical relationships."""

    g = Graph()
    g.parse(data=ttl_content, format="ttl")

    json_data = {
        "aiod_taxonomies": []
    }

    # Store elements temporarily for nesting and also for direct access
    elements_dict = {}
    broader_mapping = {}

    # Process ConceptSchemes
    for s in g.subjects(RDF.type, SKOS.ConceptScheme):
        taxonomy_id = str(g.value(s, SKOS.notation))
        taxonomy_name = str(g.value(s, RDFS.label))

        taxonomy = {
            "taxonomy_id": taxonomy_id,
            "taxonomy_name": taxonomy_name,
            "elements": []
        }
        json_data["aiod_taxonomies"].append(taxonomy)
        elements_dict[s] = taxonomy['elements']

    # First Pass: Collect all concepts
    concept_elements = {}
    for concept in g.subjects(RDF.type, SKOS.Concept):
        label_literal = g.value(concept, RDFS.label)
        if label_literal:
            label_value = str(label_literal)
            label_lang = label_literal.language if label_literal.language else "en"
        else:
            label_value = "Unknown"
            label_lang = "en"

        element = {
            "id": str(g.value(concept, SKOS.notation)),
            "label": {
                "language": label_lang,
                "value": label_value
            },
            "elements": []  # To hold narrower concepts if any
        }

        # Store element for later processing of broader relationships
        concept_elements[concept] = element

        # Handle broader relationships
        broader_concepts = list(g.objects(concept, SKOS.broader))
        if broader_concepts:
            broader_mapping[concept] = broader_concepts

        # Add the element to each relevant scheme
        for scheme in g.objects(concept, SKOS.inScheme):
            if scheme in elements_dict:
                elements_dict[scheme].append(element)

    # Second Pass: Apply broader relationships and handle nesting
    for concept, broader_concepts in broader_mapping.items():
        element = concept_elements[concept]
        for broader_concept in broader_concepts:
            broader_element = concept_elements.get(broader_concept)
            if broader_element:
                # Clone the element for each broader concept to avoid sharing issues
                element_clone = {
                    "id": element["id"],
                    "label": element["label"],
                    "elements": element["elements"].copy()
                }
                broader_element["elements"].append(element_clone)
                # Keep the element in the main list for each scheme it belongs to
                for scheme in g.objects(concept, SKOS.inScheme):
                    if scheme in elements_dict:
                        # Remove the element only if it's the last reference to avoid deletion issues in other schemes
                        if element_clone in elements_dict[scheme]:
                            elements_dict[scheme].remove(element_clone)

    return json_data

def main():
    # GitHub URL for the TTL file
    github_url = "https://raw.githubusercontent.com/aiondemand/metadata-schema/stg/taxonomies/schemas.ttl"

    # Fetch the TTL content from GitHub
    ttl_content = fetch_ttl_from_github(github_url)

    # Parse the TTL content to JSON
    json_data = parse_ttl_to_json(ttl_content)

    # Save the JSON output to a file
    with open("taxonomies.json", "w") as f:
        json.dump(json_data, f, indent=4)

    # Print the final JSON output
    print("\nFinal JSON Output:")
    print(json.dumps(json_data, indent=4))

if __name__ == "__main__":
    main()
