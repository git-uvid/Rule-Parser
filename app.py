import streamlit as st
import pandas as pd
import re
import json
import os
import networkx as nx
from pyvis.network import Network

# Function to parse JDS file
# Modified parse_jds_file to handle file content directly
def parse_jds_file(content):
    cube_name_match = re.search(r'VARIABLE_DECLARE\(CubeName;"([^"]+)"', content)
    cube_name = cube_name_match.group(1) if cube_name_match else "Cube name not found."
    content = content.replace("NO_ERROR", "$NO_ERROR")
    content = content.replace("0)", "0;")
    start_marker_match = re.search(r'VARIABLE_DEFINE\((CubeId\d+Name);\$CubeName\)', content)
    if not start_marker_match:
        raise ValueError("No dynamic start marker found in the file.")
    start_marker = start_marker_match.group(0)
    start_index = content.find(start_marker)
    if start_index == -1:
        raise ValueError(f"Start marker '{start_marker}' not found in the file.")
    content = content[start_index:]
    rule_blocks = re.findall(r'RULE_CREATE\((.*?)\$NO_ERROR', content, re.DOTALL)
    if not rule_blocks:
        raise ValueError("No RULE_CREATE entries found.")
    rule_count = len(rule_blocks)
    cols = ["Rule", "Active Status", "Comment", "Rule Position", "Template", "Type", "Unknown1", "Unknown2", "Protected"]
    ends = len(cols) + 1
    data = []
    for block in rule_blocks:
        parts = block.split(";")
        row = []
        for i in range(1, ends):  
            row.append(parts[i].strip() if i < len(parts) else "")
        data.append(row)
    
    df = pd.DataFrame(data, columns=cols)

    return cube_name, rule_count, df

# Function to save JDS to DataFrame to Excel
def save_to_excel(df, output_path):
    rule_df = df[["Rule","Active Status"]].rename(columns={"Rule": "Relationship"})
    rule_df.to_excel(output_path, sheet_name="relationship", index=False)
    return output_path
# End of JDS to Excel

# Function to parse XLS to modified XLS
def parse_xls_to_modified_xls(files):
    cube_name = files  # Dynamic file path input
    xls_filepath = f"Modified_Rules.xlsx"
    jds_filepath = f"{files}.jds"
    output_file = f"output.xlsx"

    # Logic to process the XLS file
    df = pd.read_excel(xls_filepath)
    if "Relationship" not in df.columns or "Active Status" not in df.columns:
        raise KeyError("The Excel file must contain a column named 'Relationship'.")
    relationships = []
    for entry in df['Relationship']:
        if "=" in entry:
            target, source = entry.split("=", 1)
            target = target.strip("[]").strip()
            target_measure = None
            key_value_pairs = target.split(",")
            for pair in key_value_pairs:
                if "PALO.DATA" in source:
                    if ":" in pair:
                        key, value = pair.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip().strip("'").strip()
                        if 'measure' in key:
                            match = re.search(r"\{(.*?)\}", target)
                            if match:
                                content = match.group(1).strip()
                                target_measure_set = {item.strip().strip("'") for item in content.split(",")}
                                if target_measure_set:
                                    target_measure = target_measure_set
                            else:
                                target_measure = value

            if not target_measure:
                target_measure = "All Measures"
            source_measure = None
            source_cube = cube_name
            target_cube = cube_name
            if "PALO.DATA" in source:
                match = re.search(r'PALO\.DATA\((.*?),\s*(.*?),\s*(.*?")\)', source)
                if match:
                    all_coordinates = match.group(3).strip()
                    coordinates = re.split(r',(?![^()]*\))', all_coordinates)
                    source_measure = coordinates[-1].strip().strip('"')
                    source_cube = match.group(2).strip('"')

                    if "#_" in source_cube:
                        source_cube = ""
                    target_cube = cube_name

            if not target_measure:
                target_measure = "All Measures"
            if not source_measure:
                source_measure = "All Measures"
            if not source_cube:
                source_cube = cube_name
            if isinstance(target_measure, str):
                target_measure = target_measure.strip("[]").strip()

            relationships.append({
                "Source Measure": source_measure,
                "Target Measure": target_measure,
                "Source Cube": source_cube,
                "Target Cube": target_cube,
                "Target": target,
                "Source": source
            })

    result_df = pd.DataFrame(relationships)
    filtered_df = result_df[result_df['Source'].str.contains('PALO.DATA', na=False)]
    filtered_df.to_excel(output_file, index=False)  

    return output_file

# Function to create and visualize the network graph
def create_graph_from_dataframe(df):
    G = nx.DiGraph()
    cube_nodes = {}
    edge_labels = {}
    cube_titles = {}

    filtered_df = df[df['Source'].str.contains('PALO.DATA', na=False)]

    for _, row in filtered_df.iterrows():
        source_measure, target_measure = row['Source Measure'], row['Target Measure']
        source_cube, target_cube = row['Source Cube'], row['Target Cube']

        if source_cube not in cube_nodes:
            cube_nodes[source_cube] = True
            cube_titles[source_cube] = f"Flows: {source_measure} → {target_measure}"
            G.add_node(source_cube, label=source_cube, type='cube', color='skyblue', size=35, font_size=16,
                       title=cube_titles[source_cube])
        else:
            if f"{source_measure} → {target_measure}" not in cube_titles[source_cube]:
                cube_titles[source_cube] += f" | {source_measure} → {target_measure}"
                G.nodes[source_cube]['title'] = cube_titles[source_cube]

        if target_cube not in cube_nodes:
            cube_nodes[target_cube] = True
            cube_titles[target_cube] = f"Flows: {source_measure} → {target_measure}"
            G.add_node(target_cube, label=target_cube, type='cube', color='skyblue', size=35, font_size=16,
                       title=cube_titles[target_cube])
        else:
            if f"{source_measure} → {target_measure}" not in cube_titles[target_cube]:
                cube_titles[target_cube] += f" | {source_measure} → {target_measure}"
                G.nodes[target_cube]['title'] = cube_titles[target_cube]

        edge_key = (source_cube, target_cube)

        if edge_key in edge_labels:
            edge_labels[edge_key].append(f"{source_measure} → {target_measure}")
        else:
            edge_labels[edge_key] = [f"{source_measure} → {target_measure}"]

        G.add_edge(source_cube, target_cube, color='orange', font_size=14, weight=4)

    return G, list(cube_nodes.keys())

def visualize_graph(G, output_file, title, heading):
    net = Network(notebook=True, height="800px", width="100%", directed=True)
    net.from_nx(G)

    for node in net.nodes:
        node['font'] = {'size': node.get('font_size', 12), 'color': 'black'}
        node['color'] = node.get('color', 'gray')
        node['size'] = node.get('size', 15)

    for edge in net.edges:
        edge['font'] = {'size': edge.get('font_size', 12), 'color': 'black'}
        edge['color'] = edge.get('color', 'gray')

    net.set_options(json.dumps({
        "physics": {
            "barnesHut": {
                "theta": 0.75,
                "gravitationalConstant": -20000,
                "springLength": 320,
                "springConstant": 0.16,
                "avoidOverlap": 1
            },
            "minVelocity": 0.75
        },
        "nodes": {
            "shape": "dot",
            "scaling": {"min": 10, "max": 30}
        },
        "edges": {
            "arrows": {"to": {"enabled": True}},
            "smooth": {"enabled": True, "type": "dynamic"}
        }
    }))

    html_output_path = "network_flow.html"
    net.save_graph(html_output_path)

    with open(html_output_path, "r", encoding="utf-8") as file:
        html_content = file.read()

    st.components.v1.html(html_content, height=800)

def main():
    st.title("Rules Visualizer")
    st.write("This tool allows users to upload a JDS file and visualize the data flow between cubes through an interactive graph, helping users understand the connections between different measures and cubes.")

    # File uploader widget to upload JDS file
    uploaded_file = st.file_uploader("Upload a JDS file", type=["jds"])

    if uploaded_file:
        # Read the uploaded JDS file content
        content = uploaded_file.read().decode("utf-8")
        # Parse the uploaded file
        try:
            cube_name, rule_count, rule_df = parse_jds_file(content)
            st.write(f"Cube name: {cube_name}, Rules found: {rule_count}")
            output_path = save_to_excel(rule_df, "Modified_Rules.xlsx")
            output_file = parse_xls_to_modified_xls(cube_name)
            df = pd.read_excel(output_file)
            G, cube_nodes = create_graph_from_dataframe(df)
            visualize_graph(G, output_file, "Cube Data Flow", "Data Flow Between Cubes")
        except Exception as e:
            st.error(f"Error: {e}")
    else:
        st.warning("Please upload a JDS file.")

if __name__ == "__main__":
    main()
