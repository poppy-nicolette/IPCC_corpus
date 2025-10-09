"""
author: poppy riddle
mar 20 2025
This script creates a citations.csv file from the original Excel file of OpenAlex metadata and
from the prior work in file_to_works.py.
It uses the cite_id for each work from row df['id'] and the numerical 'id' we assigned in works_df for each cited work in df['referenced_works'].
The output is a csv that has two columns: citing_id and cited_id.
Instead of their openalex id, they use the 'id' from works.csv.

Args:
    (technically none as the user is prompted)
    input_file (str): The path to the input Excel file.

Returns:
    Outputs a csv file with two columns: citing_id and cited_id.
    returns None.
"""
import pandas as pd
import os
import sys
import csv
from ast import literal_eval
import ast
from colorama import Fore,Style

def data_to_citations()->None:
    # open excel file
    input_file:str = input(Fore.LIGHTYELLOW_EX + "Enter the path to the input Excel file of OpenAlex full metadata: "+ Style.RESET_ALL)

    try:
        if input_file:
            df = pd.read_excel(input_file)
        else:
            print(Fore.LIGHTMAGENTA_EX + "No filename provided." + Style.RESET_ALL)
            sys.exit()

    except FileNotFoundError:
        print(Fore.LIGHTMAGENTA_EX + "File not found." + Style.RESET_ALL)
        sys.exit()
    except Exception as e:
        print(Fore.LIGHTMAGENTA_EX + f"An error occurred: {str(e)}" + Style.RESET_ALL)
        sys.exit()

    # new df with id and cite_id columns - this will become the works file
    df_citations = df[['id','referenced_works']].copy()
    #covert the string represention of a list into an actual list
    # could possibly just use eval() here instead of literal_eval()
    df_citations['referenced_works'] = df_citations['referenced_works'].apply(lambda x: ast.literal_eval(x))
    #explode the lists
    df_citations = df_citations.explode('referenced_works')
    #reset the index
    df_citations.reset_index(drop=True, inplace=True)

    # now, open 'data/works.csv'
    # THIS IS HARD CODED FOR NOW
    works_df = pd.read_csv('data/works.csv', dtype={'id':'int'})

    #merge df_citations with works_df to get 'id'
    df_citations = df_citations.merge(works_df[['openalex_id', 'id']],left_on='id', right_on='openalex_id', how='left')

    df_citations.drop(columns=['id_x','openalex_id'],inplace=True)
    df_citations.rename(columns={'id_y':'citing_id'}, inplace=True)

    # now let's match the 'referenced_works'
    df_citations = df_citations.merge(works_df[['openalex_id', 'id']],left_on='referenced_works', right_on='openalex_id', how='left')
    #drop unnecessary columns
    df_citations.drop(columns=['referenced_works','openalex_id'], inplace=True)
    #rename columns
    df_citations.rename(columns={'id':'cited_id'}, inplace=True)

    #drop nans in 'cited'
    df_citations.dropna(subset=['cited_id'],axis=0,inplace=True)

    #convert column 'cited_id' to int
    df_citations['citing_id'] = df_citations['citing_id'].astype(int)
    df_citations['cited_id'] = df_citations['cited_id'].astype(int)

    # save out to csv
    directory = "data"
    file_path = os.path.join(directory,"citations.csv")
    #check if dir exists
    if not os.path.exists(directory):
        os.makedirs(directory)
    df_citations.to_csv(file_path, index=False)
    print(Fore.LIGHTGREEN_EX + f"✅ Saved citations to {file_path}" + Style.RESET_ALL)

if __name__ == "__main__":
    data_to_citations()
    print(Fore.LIGHTGREEN_EX + "Citations saved successfully in data folder." + Style.RESET_ALL)
