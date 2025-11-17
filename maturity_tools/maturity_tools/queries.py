
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

commits_query = """
query($owner: String!, $repo: String!, $branch: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    ref(qualifiedName: $branch) {
      target {
        ... on Commit {
          history(first: $first, after: $after) {
            edges {
              node {
                oid
                messageHeadline
                authoredDate
                author {
                  name
                  email
                  user {
                    login
                  }
                }
                additions
                deletions
              }
            }
            pageInfo {
              endCursor
              hasNextPage
            }
          }
        }
      }
    }
  }
}
"""

releases_query = """
query($owner: String!, $repo: String!, $first_releases: Int!, $after_releases: String) {
  repository(owner: $owner, name: $repo) {
    releases(first: $first_releases, after: $after_releases, orderBy: {field: CREATED_AT, direction: DESC}) {
      totalCount
      edges {
        node {
          name
          createdAt
          tagName
          releaseAssets(first: 10) {
            edges {
              node {
                name
                downloadCount
              }
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