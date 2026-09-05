# Parameters And Expressions

## Storage

Use one native `App::VarSet` per document. Define governing dimensions and
derived formulas together in a single `define_variables` batch rather than
adding variables one at a time.

Use explicit units on every length and angle; an untyped number is not a
parameter. Use valid FreeCAD internal names: letters, digits, and
underscores, starting with a letter or underscore.

## Governing Versus Derived

A governing value is set directly and represents a real design choice. A
derived value always carries an expression that references a governing value
or another derived one; it never carries a copied number. If a derived
dimension changes only because someone remembered to update it by hand, it is
not actually derived — replace the copy with an expression.

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
