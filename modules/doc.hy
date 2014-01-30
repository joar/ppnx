(require ppnx.lib.hy)

(make-command-trigger "py")

(defn act [context]
  (try
    (do
        (setv
          (, module right)
          (get-module (second (.split context.params.trailing " " 1))))
        (setv object (get-object module right))
        (if (is object None)
          "Not found"
          (doc-format object)))
    (except [ImportError]
      "No such module")))

(defn get-object [object rest]
  (if (and object (not rest))
    object
    (try
      (if (in "." rest)
        (let [[noms (.split rest ".")]]
          (get-object
            (getattr object (car noms))
            (.join "." (cdr noms))))
        (getattr object rest))
      (except [[AttributeError]]
        None))))

(defn doc-format [object]
  (if (is None object.__doc__)
    "__doc__ is None"
    (.strip (.replace object.__doc__ "\n" " "))))

(defn get-module [nom &optional right]
  (try
    (, (__import__ nom) right)
    (except [ImportError]
      (if (in "." nom)
        (let [[(, left foo new-right) (.rpartition nom ".")]]
          (if right
            (setv new-right (.join "." [new-right right]))
            (setv new-right new-right))
          (get-module left new-right))
        (raise)))))
