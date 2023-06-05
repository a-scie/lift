# Interpreter Providers

One way Science eases assembly of scies is by providing easy access to interpreter distribution
archives. Although you can always define your own [file](#science-model-file)s, an interpreter
provider generally makes this simpler by allowing you to specify an interpreter version or some
similar small set of configuration, and then injects the file in your configuration for you
referencable by the interpreter `id` you supply in [command](science-model-command) `#{id}`
substitutions. Additionally, interpreter providers can provide keyed access to important files and
binaries within the distribution archives that you can reference via `{#id:<key>}`. The
documentation for each interpreter provider will detail both the distibution archive file keys
supported and the configuration information required.

(built-in-providers)=
```{providers}
:toctree_maxdepth: 1
:allow_raw_typenames: "no"
:allow_missing_doc: "no"
```
