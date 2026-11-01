# Database Schema

This project database schema in DBML format is available as [`database.dbml`](database.dbml).

```dbml
Table repos {
  id int [pk, increment]
  owner varchar(200) [not null]
  name varchar(200) [not null]
  default_branch varchar(200)
  created_at timestamptz [not null]

  Indexes {
    (owner, name) [unique, name: 'uq_repo_owner_name']
  }
}

Table runs {
  id int [pk, increment]
  repo_id int [not null]
  run_started_at timestamptz [not null]
  source varchar(50) [note: 'Observed value: scheduled']
  notes text
}

Table fetch_log {
  id int [pk, increment]
  repo_id int [not null]
  entity_type varchar(50) [not null, note: 'Observed values: branches, commits, issues, prs, releases']
  fetched_at timestamptz [not null]

  Indexes {
    (repo_id, entity_type) [unique, name: 'uq_fetch_repo_entity']
  }
}

Table commits {
  id int [pk, increment]
  repo_id int [not null]
  oid varchar(64) [not null]
  authored_date timestamptz
  author_login varchar(200)
  additions int
  deletions int
  message text

  Indexes {
    (repo_id, oid) [unique, name: 'uq_commit_repo_oid']
  }
}

Table branches {
  id int [pk, increment]
  repo_id int [not null]
  name varchar(200) [not null]
  last_commit_date timestamptz
  total_commits int

  Indexes {
    (repo_id, name) [unique, name: 'uq_branch_repo_name']
  }
}

Table releases {
  id int [pk, increment]
  repo_id int [not null]
  tag_name varchar(200) [not null]
  name varchar(200)
  created_at timestamptz
  total_downloads int

  Indexes {
    (repo_id, tag_name) [unique, name: 'uq_release_repo_tag']
  }
}

Table issues {
  id int [pk, increment]
  repo_id int [not null]
  github_id varchar(200) [not null]
  created_at timestamptz
  closed_at timestamptz
  state varchar(20)
  author_login varchar(200)
  first_comment_created_at timestamptz
  first_comment_author varchar(200)
  labels jsonb

  Indexes {
    (repo_id, github_id) [unique, name: 'uq_issue_repo_id']
  }
}

Table pull_requests {
  id int [pk, increment]
  repo_id int [not null]
  github_id varchar(200) [not null]
  created_at timestamptz
  merged_at timestamptz
  closed_at timestamptz
  state varchar(20)
  author_login varchar(200)
  first_comment_created_at timestamptz
  first_comment_author varchar(200)
  labels jsonb

  Indexes {
    (repo_id, github_id) [unique, name: 'uq_pr_repo_id']
  }
}

Table metrics {
  id int [pk, increment]
  run_id int [not null]
  scope varchar(50) [not null]
  name varchar(100) [not null]
  value_float float
  value_int int
  value_text text
  value_json jsonb

  Indexes {
    (run_id, scope, name) [unique, name: 'uq_metric_run_scope_name']
  }
}

Table summaries {
  id int [pk, increment]
  repo_id int
  owner varchar(200) [not null]
  summary_scope varchar(20) [not null, note: 'Observed values: repo, org']
  run_id int
  created_at timestamptz [not null]
  model varchar(200)
  prompt_version varchar(100)
  summary_text text [not null]
  metadata_json jsonb
}

Ref: runs.repo_id > repos.id
Ref: fetch_log.repo_id > repos.id
Ref: commits.repo_id > repos.id
Ref: branches.repo_id > repos.id
Ref: releases.repo_id > repos.id
Ref: issues.repo_id > repos.id
Ref: pull_requests.repo_id > repos.id
Ref: metrics.run_id > runs.id
Ref: summaries.repo_id > repos.id
Ref: summaries.run_id > runs.id
```
