"""This module contains functions to interact with the GitHub API."""
import requests
from typing import Any, Dict, Optional
from maturity_tools.queries import branches_query
import pandas as pd



def github_api_call(query: str, variables: dict, GITHUB_TOKEN):
    """
    Make a call to the github api.
    Args:
        query (str): The graphql query to make.
        variables (dict): The variables to pass to the query.
        GITHUB_TOKEN (str): The github token to use.

    Returns:
        Response of the github api.
    """
    url = 'https://api.github.com/graphql'
    headers = {
        'Authorization': f'bearer {GITHUB_TOKEN}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, headers=headers, json={'query': query, 'variables': variables})
        response.raise_for_status() # Raise an exception for bad status codes
        data = response.json()

        if 'errors' in data:
            print(f"GraphQL errors: {data['errors']}")
            return None
    except Exception as e:
        raise # we only handle if it makes sense.
    return data

def process_branches(variables, GITHUB_TOKEN) -> Optional[pd.DataFrame]:
    all_branches_data = []
    after_cursor_branches = None
    has_next_page_branches = True
    variables['first_branches'] = 100  # Number of branches to fetch per page
    variables['after_branches'] = None  # Cursor for pagination

    while has_next_page_branches:
        variables.update({"after_branches": after_cursor_branches})
        # print("Fetching branches with cursor:", after_cursor_branches) # Optional: to show progress
        data = github_api_call(branches_query, variables, GITHUB_TOKEN)

        if data and 'data' in data and data['data'] and 'repository' in data['data'] and data['data']['repository'] and 'refs' in data['data']['repository']:
            branches_data = data['data']['repository']['refs']['edges']

            # Extract required information from each branch and append to the list
            for branch_edge in branches_data:
                branch_node = branch_edge['node']
                branch_name = branch_node['name']
                commit_count = branch_node['target']['history']['totalCount'] if branch_node['target'] and 'history' in branch_node['target'] else None
                last_commit_date = branch_node['target']['authoredDate'] if branch_node['target'] and 'authoredDate' in branch_node['target'] else None

                all_branches_data.append({
                    'branch_name': branch_name,
                    'total_commits': commit_count,
                    'last_commit_date': last_commit_date
                })

            page_info_branches = data['data']['repository']['refs']['pageInfo']
            after_cursor_branches = page_info_branches['endCursor']
            has_next_page_branches = page_info_branches['hasNextPage']
        else:
            print("Error: Could not retrieve branch data or unexpected data structure.")
            break

    print(f"Fetched details for {len(all_branches_data)} branches.")

    # Create a pandas DataFrame from the collected data
    df_branches = pd.DataFrame(all_branches_data)

    # Convert 'last_commit_date' to datetime objects
    df_branches['last_commit_date'] = pd.to_datetime(df_branches['last_commit_date'])
    return df_branches