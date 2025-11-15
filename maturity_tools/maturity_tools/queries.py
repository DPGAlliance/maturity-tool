
repo_info_query = """
query($owner: String!, $repo: String!) {
  repository(owner: $owner, name: $repo) {
    defaultBranchRef {
      name
    }
    stargazerCount
    forkCount
    watchers {
      totalCount
    }
    issues(states: OPEN) {
      totalCount
    }
    closedIssues: issues(states: CLOSED) {
      totalCount
    }
  }
}
"""

branches_query = """
query($owner: String!, $repo: String!, $first_branches: Int!, $after_branches: String) {
  repository(owner: $owner, name: $repo) {
    refs(first: $first_branches, after: $after_branches, refPrefix: "refs/heads/") {
      totalCount
      edges {
        node {
          name
          target {
            ... on Commit {
              history {
                totalCount
              }
              authoredDate
            }
          }
        }
      }
      pageInfo {
        endCursor
        hasNextPage
      }
    }
  }
}
"""