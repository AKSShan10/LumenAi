import { Fragment, useState } from "react";

// One table for the whole app, with pagination.
//
//   <DataTable
//     columns={[{ key: "title", title: "Title" },                                  // shows row.title
//               { key: "added", title: "Added", render: (row) => day(row.created_at), className: "small" }]}
//     rows={items}                 // all rows; the table shows one page of them
//     rowKey={(row) => row.id}     // a unique key per row (default: row.id)
//     empty="Nothing here yet."    // shown when there are no rows
//     pageSize={10}                // rows per page (default 10)
//     expanded={(row) => ...}      // optional: an extra full-width row under a row (or null for none)
//   />
//
// render(row, index) gets the row's place in the WHOLE list (0 = first), so a rank stays right on page 2.
export default function DataTable({ columns, rows, rowKey = (row) => row.id, empty = "Nothing to show.",
                                    pageSize = 10, expanded }) {
  const [page, setPage] = useState(1);
  if (rows.length === 0) return <p className="muted small">{empty}</p>;

  const pages = Math.ceil(rows.length / pageSize);
  const current = Math.min(page, pages);            // the list got shorter (a delete): stay on a page that exists
  const first = (current - 1) * pageSize;
  const shown = rows.slice(first, first + pageSize);

  return (
    <>
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column.key}>{column.title}</th>)}</tr>
        </thead>
        <tbody>
          {shown.map((row, place) => {
            const index = first + place;
            const extra = expanded ? expanded(row) : null;
            return (
              <Fragment key={rowKey(row)}>
                <tr>
                  {columns.map((column) => (
                    <td key={column.key} className={column.className}>
                      {column.render ? column.render(row, index) : row[column.key]}
                    </td>
                  ))}
                </tr>
                {extra && <tr><td colSpan={columns.length} className="small">{extra}</td></tr>}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {pages > 1 && (
        <div className="pager">
          <button type="button" className="secondary" onClick={() => setPage(current - 1)} disabled={current === 1}>Previous</button>
          <span className="muted small">Page {current} of {pages} ({rows.length} rows)</span>
          <button type="button" className="secondary" onClick={() => setPage(current + 1)} disabled={current === pages}>Next</button>
        </div>
      )}
    </>
  );
}
