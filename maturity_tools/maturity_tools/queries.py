
repo_info_query = """
query($owner: String!, $repo: String!) {
  repository(owner: $owner, name: $repo) {
    createdAt
    updatedAt
    isArchived
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
    pullRequests(states: OPEN) {
      totalCount
    }
    closedPullRequests: pullRequests(states: CLOSED) {
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
              oid
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
query($owner: String!, $repo: String!, $branch: String!, $first: Int!, $after: String, $since: GitTimestamp) {
  repository(owner: $owner, name: $repo) {
    ref(qualifiedName: $branch) {
      target {
        ... on Commit {
          history(first: $first, after: $after, since: $since) {
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

issues_query = """
query($owner: String!, $repo: String!, $first_issues: Int!, $after_issues: String, $since: DateTime) {
  repository(owner: $owner, name: $repo) {
    issues(first: $first_issues, after: $after_issues, states: [OPEN, CLOSED], filterBy: {since: $since}) {
      edges {
        node {
          id
          title
          createdAt
          closedAt
          state
          author {
            login
          }
          comments(first: 1) {
            nodes {
              author {
                login
              }
              createdAt
            }
          }
          labels(first: 100) {
            nodes {
              name
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

governance_query = """
query($owner: String!, $repo: String!) {
  repository(owner: $owner, name: $repo) {
    security_md: object(expression: "HEAD:SECURITY.md") { __typename }
    security_rst: object(expression: "HEAD:SECURITY.rst") { __typename }
    security_txt: object(expression: "HEAD:.github/SECURITY.md") { __typename }
    governance_md: object(expression: "HEAD:GOVERNANCE.md") { __typename }
    governance_rst: object(expression: "HEAD:GOVERNANCE.rst") { __typename }
    code_of_conduct_md: object(expression: "HEAD:CODE_OF_CONDUCT.md") { __typename }
    code_of_conduct_gh: object(expression: "HEAD:.github/CODE_OF_CONDUCT.md") { __typename }
    dockerfile: object(expression: "HEAD:Dockerfile") { __typename }
    docker_compose_yml: object(expression: "HEAD:docker-compose.yml") { __typename }
    docker_compose_yaml: object(expression: "HEAD:docker-compose.yaml") { __typename }
    containerfile: object(expression: "HEAD:Containerfile") { __typename }
  }
}
"""

pr_query = """
query($owner: String!, $repo: String!, $first_prs: Int!, $after_prs: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: $first_prs, after: $after_prs, states: [OPEN, CLOSED, MERGED], orderBy: {field: CREATED_AT, direction: DESC}) {
      edges {
        node {
          id
          title
          createdAt
          mergedAt
          closedAt
          state
          author {
            login
          }
          comments(first: 1) {
            nodes {
              author {
                login
              }
              createdAt
            }
          }
          labels(first: 100) {
            nodes {
              name
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
