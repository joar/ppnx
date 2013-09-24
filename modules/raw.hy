(defn trigger [context]
  (and
    context.is_admin
    context.params.trailing
    (= (slice context.params.trailing 0 4) "!raw")))

(defn act [context]
  (.split (slice context.params.trailing 5) " "))
