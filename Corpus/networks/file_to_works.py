"""
author: poppy riddle
mar 20 2025
This file opens an excel spreadsheet of openalex full metadata.
for each row, it creates a new 'works' file that contains the 'id' and all ids in 'referenced_works'.
the 'referenced_works' are the 'id' of the works that are cited in the 'id' work and need to be
unpacked as the are in a list.
The works file should include two columns: 'id' and 'cite_id'
The works file should be saved as a csv in the 'data' subfolder.

Args:
    filename: str - the name of the Excel file to open. You will be prompted to enter the filename.capitalize

Returns:
    Saves out a csv file in the 'data' subfolder.
    returns None
"""
import pandas as pd
import os
import sys
import csv
from ast import literal_eval
import ast
from colorama import Fore, Style

# open excel file
# need to change this to accept a file rather than hardcode the file name
# add try except to deal with exceptions
def data_to_works()->None:
    filename = input("what is the Excel filename: ")
    try:
        if filename:
            df = pd.read_excel(filename)
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
    works_df = pd.DataFrame(columns=['openalex_id', 'id'])

    # iterate through each row in the excel file.
    # for each row take the value from df['id'] and add it to works_df['openalex_id']
    for index,row in df.iterrows():
        if pd.notnull(row['id'] and row['id']!=''):
            works_df = pd.concat([works_df, pd.DataFrame({'openalex_id': row['id'], 'id': None}, index=[0])], ignore_index=True)

    # iterate through each row in df['referenced_works']
    """ It turns out what appeared to be a nested list was a string representation of a nested list.
    Due to the way zotero exported or I imported the file into Excel.
    Used ast.literal_eval() to convert to list
    then used extend to create a flat list.
    """
    referenced_works = []
    # convert df['referenced_works'] into a list
    for row in df['referenced_works']:
        #convert string representation to a list type
        row_list = ast.literal_eval(row)
        #append to a flat list
        referenced_works.extend(row_list)

    # create a new DataFrame with the items in new_list
    ref_works = pd.DataFrame(referenced_works, columns=['openalex_id'])

    # concatenate ref_works with works_df
    works_df = pd.concat([works_df, ref_works], ignore_index=True)

    # add sequential number for cite_id
    works_df['id'] = works_df.reset_index().index+1
    works_df['id'] = works_df['id'].astype(int)

    # save out to csv
    directory = "data"
    file_path = os.path.join(directory,"works.csv")
    #check if dir exists
    if not os.path.exists(directory):
        os.makedirs(directory)
    works_df.to_csv(file_path, index=False)
    print(Fore.LIGHTGREEN_EX + f"✅ file_to_works function complete. File saved: {file_path}" + Style.RESET_ALL)

if __name__ == '__main__':
    data_to_works()
    print(Fore.LIGHTCYAN_EX + "All done!" + Style.RESET_ALL)
