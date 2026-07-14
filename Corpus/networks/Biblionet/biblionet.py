#biblionet.py
"""
author: poppy riddle, phil mongeon, geoff kraus
date: April 2025
version:1.4
developed from Phil Mongeon's R code here:
Purpose:
    to take two input files that come from 'file_to_works.py' and 'citations.py'
    there are two files that should be in a 'data' subfolder:
        citations.csv
        works.csv
    The methods allow for the creation of network files that can be used for network analysis.

Args:
    citations.csv
    works.csv

Returns:
    network files located in a 'networks' subfolder that can be used for network analysis such as:
        edge list as net_(type).csv
        node list as nodes_(type).csv
    Example:
        net_bc.csv
        nodes_bc.csv

Usage:
    analysis = BiblioNet(works_file,citations_file)
    analysis.load_data()
    analysis.clean_data()
    #basic networks
    analysis.net_bc()
    analysis.net_dc()
    analysis.net_cc()
    #hybrid versions
    analysis.net_bc_cc_dc()
    analysis.net_bc_dc()
    analysis.net_cc_dc()
    analysis.nodes_export()
"""
import argparse
import glob
import pandas as pd
from colorama import Fore,Style
import os
import igraph as ig
import leidenalg as la


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
        try:
            self.works = pd.read_csv(self.works_file)
        except FileNotFoundError:
            print(Fore.LIGHTRED_EX + f"File {self.works_file} not found" + Style.RESET_ALL)
        except pd.errors.EmptyDataError:
            print(Fore.LIGHTRED_EX + f"File {self.works_file} is empty" + Style.RESET_ALL)
        except pd.errors.ParserError:
            print(Fore.LIGHTRED_EX + f"Parse error in {self.works_file}" + Style.RESET_ALL)
        except Exception as e:
            print(Fore.LIGHTRED_EX + "Attempt to open {self.works_file} resulted in exception: {e}" + Style.RESET_ALL)

        #Normalize the OpenAlex id column name. The sample works.csv calls it
        #'openalex_id'; the full works_full.csv calls it 'openalex_work_id'. The rest
        #of the code (nodes_export merge, Label rename) expects 'openalex_id', so we
        #standardize to that here rather than editing the CSVs. Accept either spelling.
        if self.works is not None and 'openalex_id' not in self.works.columns:
            for alt in ('openalex_work_id', 'openalex_work', 'openalex'):
                if alt in self.works.columns:
                    self.works = self.works.rename(columns={alt: 'openalex_id'})
                    break

        try:
            self.citations = pd.read_csv(self.citations_file)
        except FileNotFoundError:
            print(Fore.LIGHTRED_EX + f"File {self.citations_file} not found" + Style.RESET_ALL)
        except pd.errors.EmptyDataError:
            print(Fore.LIGHTRED_EX + f"File {self.citations_file} is empty" + Style.RESET_ALL)
        except pd.errors.ParserError:
            print(Fore.LIGHTRED_EX + f"Parse error in {self.citations_file}" + Style.RESET_ALL)
        except Exception as e:
            print(Fore.LIGHTRED_EX + f"Attempt to open {self.citations_file} resulted in exception: {e}" + Style.RESET_ALL)


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
            net_bc.drop(columns=['citing_id'], inplace=True)
            #SECOND JOIN
            net_bc = net_bc.merge(self.citations, on='cited_id', how='inner')
            #only keeps those that match
            net_bc = net_bc[net_bc['citing_id'].isin(self.works['id'])]
            #renames columns
            net_bc = net_bc[['id', 'citing_id']].rename(columns={'id': 'source', 'citing_id': 'target'})
            #cast ids to int BEFORE the source<target dedup so ordering is numeric,
            #not lexicographic ("100" < "99" as strings flips the edge orientation).
            net_bc['source'] = net_bc['source'].astype(int)
            net_bc['target'] = net_bc['target'].astype(int)
            #filter for source < target (numeric)
            net_bc = net_bc[net_bc['source']<net_bc['target']]
            #add weight
            net_bc['weight'] = 1
            #summarize weight using groupby, then apply sum, then reset_index to restore to a df
            net_bc = net_bc.groupby(['source','target']).agg({'weight':'sum'}).reset_index()
            # undirected at this point
            net_bc['type'] = 'undirected' #note undirected
            #export to csv
            self.export_edges(net_bc, "net_bc.csv")
            #save as an instance variable for use later
            self._net_bc = net_bc
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
            #cast ids to int BEFORE the source<target dedup so ordering is numeric,
            #not lexicographic ("100" < "99" as strings flips the edge orientation).
            filtered_citations['source'] = filtered_citations['source'].astype(int)
            filtered_citations['target'] = filtered_citations['target'].astype(int)
            #filter where source is less than target (numeric): r: filter(source < target)
            filtered_citations = filtered_citations[filtered_citations['source']<filtered_citations['target']]
            # groupby 'source' and 'target' in that order, and use size() as equivalent for summarize
            net_cc = filtered_citations.groupby(['source','target']).size().reset_index(name='weight')
            #print(f"after groupby:\n{net_cc.head(2)}")
            #add type col with value 'undirected'
            net_cc['type'] = 'undirected'
            #print(f"added undirected in type: \n{net_cc.head(2)}")

            self.export_edges(net_cc, "net_cc.csv")
            #assign to instance variable
            self._net_cc = net_cc
        return self._net_cc


    @staticmethod
    def _hybrid_undirected(parts):
        #combine one or more edge frames into a single UNDIRECTED weighted edge list.
        #
        #Every edge is canonicalized to (source = min id, target = max id) BEFORE the
        #weight sum. This does two things:
        #  1. A directed DC edge a->b and its reciprocal b->a collapse onto the same
        #     {a,b} pair, so their weights add (reciprocal citations -> weight 2).
        #  2. DC aligns with the already-undirected BC/CC edges on the same node pair,
        #     so the hybrid carries one weighted edge per pair, not one per orientation.
        #BC and CC are already min<max oriented, so this is a no-op for them.
        combined = pd.concat(parts)[['source', 'target', 'weight']].copy()
        lo = combined[['source', 'target']].min(axis=1)
        hi = combined[['source', 'target']].max(axis=1)
        combined['source'] = lo
        combined['target'] = hi
        return combined.groupby(['source', 'target']).agg({'weight': 'sum'}).reset_index()

    def net_bc_cc_dc(self):
        #creates hybrid BC-CC-DC edges (undirected, weights summed across types)
        net_bc_cc_dc = self._hybrid_undirected([self._net_bc, self._net_dc, self._net_cc])
        self.export_edges(net_bc_cc_dc, "net_bc_cc_dc.csv")

    def net_bc_cc(self):
        #creates hybrid BC-CC edges (undirected, weights summed across types)
        # net_bc_cc <- bind_rows(net_cc, net_bc) %>%
        # group_by(source, target) %>% summarize(weight = sum(weight))
        net_bc_cc = self._hybrid_undirected([self._net_bc, self._net_cc])
        self.export_edges(net_bc_cc, "net_bc_cc.csv")

    def net_bc_dc(self):
        #creates hybrid BC-DC edges (undirected, weights summed across types)
        # net_bc_dc <- bind_rows(net_bc, net_dc) %>%
        # group_by(source, target) %>% summarize(weight = sum(weight))
        net_bc_dc = self._hybrid_undirected([self._net_bc, self._net_dc])
        self.export_edges(net_bc_dc, "net_bc_dc.csv")

    def net_cc_dc(self):
        #creates hybrid CC-DC edges (undirected, weights summed across types)
        #net_cc_dc <- bind_rows(net_cc, net_dc) %>%
        # group_by(source, target) %>% summarize(weight = sum(weight))
        net_cc_dc = self._hybrid_undirected([self._net_cc, self._net_dc])
        self.export_edges(net_cc_dc, "net_cc_dc.csv")


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

    def nodes_export(self, closeness_max_nodes=50000, seed=42):
        #computes node-level attributes (components, clusters, centralities) per network.
        #
        #Moved off networkx to igraph/leidenalg for the full-scale (666K-node DC) graph:
        #  - networkx louvain_communities / greedy_modularity_communities do not scale;
        #    igraph's multilevel (Louvain) and leidenalg (Leiden) are C-backed and fast.
        #  - closeness_centrality is O(V*E) and will not finish on DC; it is skipped above
        #    closeness_max_nodes (set to None to force it everywhere).
        #  - eigenvector uses igraph's ARPACK solver, which does not suffer the
        #    non-convergence of networkx's power-iteration eigenvector_centrality.
        #
        # List files in the directory and filter those that start with "net_"
        net_files = [f for f in os.listdir("networks/") if f.startswith("net_")]

        #make igraph's RNG reproducible so Louvain/Leiden labels are stable across runs
        try:
            ig.set_random_number_generator(__import__('random'))
            __import__('random').seed(seed)
        except Exception:
            pass  # older igraph without a settable RNG; clustering still works

        for file in net_files:
            # Read the CSV file into a DataFrame
            df = pd.read_csv(os.path.join("networks", file))
            print(f".....calculating nodes for {file}...")

            #build an undirected igraph from the edge list; vertex names are the work ids.
            #use_vids=False -> the source/target *values* become vertex 'name' attributes,
            #and the extra columns (weight, type) ride along as edge attributes.
            g = ig.Graph.DataFrame(df[['source', 'target', 'weight']],
                                   directed=False, use_vids=False)
            names = g.vs['name']
            n = g.vcount()

            #components: membership is a per-vertex list, index-aligned to g.vs
            comp = g.connected_components().membership

            #Louvain (weighted) — igraph multilevel, the scalable replacement
            louvain = g.community_multilevel(weights='weight').membership

            #Leiden (weighted), modularity objective — real Leiden now, via leidenalg.
            #The old code's 'cluster_leiden' column was greedy_modularity as a proxy;
            #this column is now genuinely Leiden, so the data dictionary can say so.
            leiden = la.find_partition(g, la.ModularityVertexPartition,
                                       weights='weight', seed=seed).membership

            #degree (unweighted node degree), matching the original
            degree = g.degree()

            #closeness and eigenvector are computed UNWEIGHTED to match the original
            #networkx calls (which passed no weight); note igraph would otherwise treat
            #'weight' as a distance, which is wrong for similarity edges.
            if closeness_max_nodes is not None and n > closeness_max_nodes:
                print(f"      (skipping closeness: {n} nodes > {closeness_max_nodes})")
                closeness = [float('nan')] * n
            else:
                closeness = g.closeness()  # unweighted, hop-based

            eigen = g.eigenvector_centrality(weights=None)  # ARPACK, unweighted

            #assemble nodes_df; all lists are index-aligned to the igraph vertex order
            nodes_df = pd.DataFrame({
                "id": names,
                "component": comp,
                "cluster_louvain": louvain,
                "cluster_leiden": leiden,
                "degree": degree,
                "closeness": closeness,
                "eigen_centrality": eigen,
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
    print("..........calculating cc_dc edges...")
    analysis.net_cc_dc()
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
