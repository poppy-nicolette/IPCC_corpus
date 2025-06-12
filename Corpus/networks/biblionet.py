#biblionet.py
"""
author: poppy riddle
date: April 2025
version:1.2
developed from Phil Mongeon's R code here:
Purpose:
    to take two input files that come from 'file_to_works.py' and 'citations.py'
    there are two files that should be in a data subfolder:
        citations.csv
        works.csv
    The methods allow for the creation of network files that can be used for network analysis..

Args:
    citations.csv
    works.csv

Returns:
    network files that can be used for network analysis such as:
        edge list as net_(type).csv
        node list as nodes_(type).csv
    Example:
        net_bc.csv
        nodes_bc.csv

Usage:
    analysis = BiblioNet(works_file,citations_file)
    analysis.load_data()
    analysis.clean_data()
    analysis.net_bc()
    analysis.net_dc()
    analysis.nodes_export()
"""
import argparse
import glob
import pandas as pd
from colorama import Fore,Style
import os
import networkx as nx
from networkx.algorithms.community import louvain_communities, greedy_modularity_communities
from networkx.algorithms.centrality import closeness_centrality, eigenvector_centrality


class BiblioNet:
    def __init__(self, works_file, citations_file):
        self.works_file = works_file
        self.citations_file = citations_file
        self.works = None
        self.citations = None
        #internal instance variables
        self._net_bc = None
        self._net_dc = None
        self._net_cc = None

    def load_data(self)->None:
        #loads files into dataframes
        self.works = pd.read_csv(self.works_file)
        self.citations = pd.read_csv(self.citations_file)


    def clean_data(self):
        # Fix data types to make sure all are string - could expand to check before doing this
        self.works['id'] = self.works['id'].astype(str)
        self.citations['citing_id'] = self.citations['citing_id'].astype(str)
        self.citations['cited_id'] = self.citations['cited_id'].astype(str)

    def net_bc(self):
        #creates the bibliographic coupling edges
        #merges work id and citations on citing id
        if self._net_bc is None:
            net_bc = self.works[['id']].merge(self.citations, left_on='id', right_on='citing_id', how='inner')
            #only keeps those that match
            net_bc = net_bc[net_bc['citing_id'].isin(self.works['id'])]
            #renames columns
            net_bc = net_bc[['id', 'cited_id']].rename(columns={'id': 'source', 'cited_id': 'target'})
            #add weight
            net_bc['weight'] = 1
            # undirected at this point
            net_bc['type'] = 'undirected' #note undirected
            #makes both int just to be sure.
            net_bc['source'] = net_bc['source'].astype(int)
            net_bc['target'] = net_bc['target'].astype(int)

            self.export_edges(net_bc, "net_bc.csv")
            #save as an instance variable for use later
            self.net_bc = net_bc
        return self._net_bc

    def net_dc(self):
        #creates direct citation edges, using a mask, probably don't need this step
        # but it might be necessary for certain citations files that extend beyond core works
        if self._net_dc is None:
            net_dc = self.citations[
                self.citations['citing_id'].isin(self.works['id']) &
                self.citations['cited_id'].isin(self.works['id'])
            ]
            #rename cols
            net_dc = net_dc.rename(columns={'citing_id':'source', 'cited_id':'target'})
            #add weight and type cols
            net_dc = net_dc.assign(weight=1, type='directed')
            #remove dupes
            net_dc = net_dc.drop_duplicates() # should this add instead of drop?
            #make sure they're both int
            net_dc['source'] = net_dc['source'].astype(int)
            net_dc['target'] = net_dc['target'].astype(int)

            self.export_edges(net_dc, "net_dc.csv")
            #assign to instance variable
            self._net_dc = net_dc
        return self._net_dc

    def net_cc(self):
        #creates co-citation edges
        # just get one column
        if self._net_cc is None:
            works_id = self.works['id']
            #first inner join on 'id' and 'cited_id'
            joined_citations = pd.merge(works_id, self.citations, left_on='id', right_on= 'cited_id', how='inner')
            #second inner join on 'citing_id'
            joined_citations = pd.merge(joined_citations, self.citations, on='citing_id', how='inner')
            #print(f"after second join: \n{joined_citations.head(2)}")
            #filter - could have done this first?
            filtered_citations = joined_citations[joined_citations['cited_id_y'].isin(joined_citations['id'])]
            #rename cols
            filtered_citations = filtered_citations.rename(columns={'cited_id_x':'source', 'cited_id_y':'target'})
            #print(f"after rename cols: \n{filtered_citations.head(2)}")
            #filter where source is less than target r:  filter(source < target)
            # i don't totally understand this, becuase these are ids?
            filtered_citations = filtered_citations[filtered_citations['source']<filtered_citations['target']]
            # groupby 'source' and 'target' in that order, and use size() as equivalent for summarize
            net_cc = filtered_citations.groupby(['source','target']).size().reset_index(name='weight')
            #print(f"after groupby:\n{net_cc.head(2)}")
            #add type col with value 'undirected'
            net_cc['type'] = 'undirected'
            #print(f"added undirected in type: \n{net_cc.head(2)}")
            #convert to ints
            net_cc['source'] = net_cc['source'].astype(int)
            net_cc['target'] = net_cc['target'].astype(int)

            self.export_edges(net_cc, "net_cc.csv")
            #assign to instance variable
            self._net_cc = net_cc
        return self._net_cc


    def net_bc_cc_dc(self):
        #creates hybrid BC-CC-DC edges
        net_bc = self._net_bc
        net_dc = self._net_dc
        net_cc = self._net_cc

        #concat together all three
        net_bc_cc_dc = pd.concat([net_bc, net_dc, net_cc])
        #groupby and then create new column weight with agg which sums weight for each group
        net_bc_cc_dc = net_bc_cc_dc.groupby(['source','target']).agg({'weight':'sum'}).reset_index()
        #export
        self.export_edges(net_bc_cc_dc, "net_bc_cc_dc.csv")

    def net_bc_cc(self):
        #creates hybrid BC-CC edges
        # net_bc_cc <- bind_rows(net_cc, net_bc) %>%
        # group_by(source, target) %>%
        # summarize(weight = sum(weight))
        net_bc = self._net_bc
        net_cc = self._net_cc
        # contact both together
        net_bc_cc = pd.concat([net_bc, net_cc])
        #same as above for group and sum weight
        net_bc_cc = net_bc_cc.groupby(['source','target']).agg({'weight':'sum'}).reset_index()
        #export
        self.export_edges(net_bc_cc, "net_bc_cc.csv")

    def net_bc_dc(self):
        #creates hybrid BC-DC edges
        # net_bc_dc <- bind_rows(net_bc, net_dc) %>%
        # group_by(source, target) %>%
        # summarize(weight = sum(weight))
        net_bc = self._net_bc
        net_dc = self._net_dc
        #concat both together
        net_bc_dc = pd.concat([net_bc, net_dc])
        # same as above for group and sum weight
        net_bc_dc = net_bc_dc.groupby(['source','target']).agg({'weight':'sum'}).reset_index()
        #export
        self.export_edges(net_bc_dc, "net_bc_dc.csv")


    def net_cc_dc(self):
        #creates hybrid CC-DC edges
        #net_cc_dc <- bind_rows(net_cc, net_dc) %>%
        # group_by(source, target) %>%
        # summarize(weight = sum(weight))
        net_cc = self._


    def export_edges(self, df, file_name):
        #exports to csv
        directory = "networks"
        #construct file path
        file_path = os.path.join(directory, file_name)
        #check if dir exists
        if not os.path.exists(directory):
            os.makedirs(directory)
        #write file
        df.to_csv(file_path,encoding="utf-8",index=False)
        print(Fore.LIGHTCYAN_EX + f"✅ Exported {file_name} file as {file_path}" + Style.RESET_ALL)

    def nodes_export(self):
        #creates the bibliographic coupling nodes
        # List files in the directory and filter those that start with "net_"
        net_files = [f for f in os.listdir("networks/") if f.startswith("net_")]

        for file in net_files:
            # Read the CSV file into a DataFrame
            df = pd.read_csv(os.path.join("networks", file))
            print(f".....calculating nodes for {file}...")

            #create a graph from the DataFrame, uses column names for attributes
            network = nx.from_pandas_edgelist(df, source='source', target='target', edge_attr='weight')

            #components - see documentation in NetworkX for the enumeration comprehension
            #copied and pasted from documentation
            components = list(nx.connected_components(network))
            component_map = {node: idx for idx, component in enumerate(components) for node in component}
            nx.set_node_attributes(network, component_map, 'comp')

            #louvain clusters, note last line in nx.set_node_attributes
            louvain_clusters = list(louvain_communities(network, weight='weight'))
            cluster_map = {node: idx for idx, cluster in enumerate(louvain_clusters) for node in cluster}
            nx.set_node_attributes(network, cluster_map, 'cluster_louvain')

            #Phil's code uses leiden clusters (using greedy modularity as a proxy)
            #update this to use leidenalg in the future
            leiden_clusters = list(greedy_modularity_communities(network, weight='weight'))
            cluster_map = {node: idx for idx, cluster in enumerate(leiden_clusters) for node in cluster}
            nx.set_node_attributes(network, cluster_map, 'cluster_leiden')

            # degree, closeness, and eigen centrality
            degree_dict = dict(network.degree())
            closeness_dict = closeness_centrality(network)
            eigen_dict = eigenvector_centrality(network)

            #from NetworkX tutorial
            nx.set_node_attributes(network, degree_dict, 'degree')
            nx.set_node_attributes(network, closeness_dict, 'closeness')
            nx.set_node_attributes(network, eigen_dict, 'eigen_centrality')

            #create final nodes_df with node attributes
            nodes_df = pd.DataFrame({
                "id": list(network.nodes()),
                "component": [network.nodes[node]['comp'] for node in network.nodes()],
                "cluster_louvain": [network.nodes[node]['cluster_louvain'] for node in network.nodes()],
                "cluster_leiden": [network.nodes[node]['cluster_leiden'] for node in network.nodes()],
                "degree": [network.nodes[node]['degree'] for node in network.nodes()],
                "closeness": [network.nodes[node]['closeness'] for node in network.nodes()],
                "eigen_centrality": [network.nodes[node]['eigen_centrality'] for node in network.nodes()]
            })

            #add an openalex id to the nodes for identification later in the visualization
            #match these on works.csv which is already imported as a df 'works'
            nodes_df['id'] = nodes_df['id'].astype(str)
            self.works['id'] = self.works['id'].astype(str)
            nodes_df = nodes_df.merge(self.works[['id','openalex_id']], on='id', how='left')

            #rename 'openalex_id' as 'Label'
            nodes_df = nodes_df.rename(columns={'openalex_id':'Label'})

            # Write the results to a new CSV file
            output_file = os.path.join("networks", file.replace("net", "nodes"))
            nodes_df.to_csv(output_file, index=False)
            print(Fore.LIGHTGREEN_EX + f"✅ Exported file as {output_file}" + Style.RESET_ALL)


def main(works_file, citations_file):
    analysis = BiblioNet(works_file,citations_file)
    print(Fore.LIGHTMAGENTA_EX + "loading data...")
    analysis.load_data()
    print("...cleaning...")
    analysis.clean_data()
    print("....calculating bc edges...")
    analysis.net_bc()
    print(".....calculating dc edges...")
    analysis.net_dc()
    print(".......calculating cc edges...")
    analysis.net_cc()
    print(".......calculating bc_dc_cc edges....")
    analysis.net_bc_cc_dc()
    print("........calculating bc_cc edges...")
    analysis.net_bc_cc()
    print(".........calculating bc_dc edges...")
    analysis.net_bc_dc()
    print(Fore.LIGHTMAGENTA_EX + ".....calculating nodes..this can take a while..."+ Style.RESET_ALL)
    analysis.nodes_export()
    print(Fore.LIGHTBLUE_EX + "All complete! Thank you for shopping at S-Mart!" + Style.RESET_ALL)

if __name__ == '__main__':
    #set up parser
    parser = argparse.ArgumentParser(description = "Run BiblioNet analysis")
    parser.add_argument("works_file", type=str, help="Path to the works csv file.")
    parser.add_argument("citations_file", type=str, help="Path to the citations csv file.")
    #parse args
    args = parser.parse_args()

    #run main()
    main(args.works_file, args.citations_file)
