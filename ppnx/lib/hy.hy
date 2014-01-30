(defmacro make-command-trigger [command]
  `(defn trigger [context]
    (and
      context.params.trailing
      (.startswith
        context.params.trailing
        (.join
          ""
          (,
            "!"
            ~command))))))
