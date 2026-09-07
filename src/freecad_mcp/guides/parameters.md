# Parameters And Expressions

## Storage

Use one native `App::VarSet` per document. Define governing dimensions and
derived formulas together in a single `define_variables` batch rather than
adding variables one at a time.

Use explicit units on every length and angle; an untyped number is not a
parameter. Use valid FreeCAD internal names: letters, digits, and
underscores, starting with a letter or underscore.

## Governing, Derived, Incidental

Which category a value falls into is decided in the design brief, not here.
See `freecad://guide/brief`. This is what each one becomes in the document.

A **governing** value is set directly and represents a real design choice. It
becomes a variable in the `App::VarSet`.

A **derived** value always carries an expression referencing a governing
value or another derived one; it never carries a copied number. It becomes a
variable too. If a derived dimension changes only because someone remembered
to update it by hand, it is not actually derived — replace the copy with an
expression.

An **incidental** value is not a parameter and does not become a variable.
Write it into the sketch or feature directly. A variable nobody will ever
change is a control that does nothing when edited, which is worse than its
absence because it invites someone to try. `validate_document` reports the
variables that drive nothing.

## Binding Expressions

Call `bind_expressions` once for a related group of feature properties or
sketch dimensions rather than binding them individually. Constraint paths use
forms such as `Constraints[8]`, and qualified variable references use forms
such as `Variables.tower_height`.

## Rejection Is Atomic

A rejected batch reports each failing property and expression, and rolls back
every definition in that batch — a partially applied batch never remains. Read
the reported failures, fix the smallest responsible expression or unit, and
resubmit the batch rather than trying to patch one variable at a time.
