(require ppnx.lib.hy)

(make-command-trigger "help")

(defn act [context]
  (.format "\x01ACTION {0}\x01"
    (.join " " (,
      "is an IRC bot running on the xudd python actor model system"
      "(https://github.com/xudd/xudd), you can get my code at"
      "https://github.com/joar/ppnx"))))
