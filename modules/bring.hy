(require ppnx.lib.hy)

(make-command-trigger "bring")

(defn act [context]
  (setv subject (slice context.params.trailing 7))
  (.format "\x01ACTION brings {0}\x01" subject))
