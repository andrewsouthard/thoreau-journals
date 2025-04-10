#!/bin/sh

files=(index.html styles.css favicon.ico  thoreau_journals.db)
for item in "${files[@]}"
do
   bun x wrangler r2 object put --remote thoreau-journals/$item -f $item
done
