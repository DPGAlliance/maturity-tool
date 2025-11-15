This is a monorepo with two python packages:
- maturity_tools: A package with tools to assess data maturity.
- data_viewer: A package with tools to visualize the results of data maturity assessment.

They are separate to allow maturity_tools to be used as a dependency in other projects without bringing in streamlit and other visualization dependencies.


They will both have their own README files.