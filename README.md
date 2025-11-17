This is a monorepo with two python packages:
- maturity_tools: A package with tools to assess data maturity.
- data_viewer: A package with tools to visualize the results of data maturity assessment.

They are separate to allow maturity_tools to be used as a dependency in other projects without bringing in streamlit and other visualization dependencies.


They will both have their own README files.


### Notes
- we have some repetitions that should be abstracted. (asap)
- some projects are huge: getting all the branches and commits can take a long time
    i we should add a selectorn on how long we want to check back. this whole thing is for testing/demoing the features. make it fast, and if we need details, we will give the time for it.
- some queries have no pagination but shouls have the same structure as the rest. (query, process, cache is optimal. dont call the api directly from main.)