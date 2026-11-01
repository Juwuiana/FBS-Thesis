function downloadImportCredentials(credentials) {
  if (!Array.isArray(credentials) || credentials.length === 0) return;

  // Quote every cell, and defuse spreadsheet formulas (=, +, -, @) in names/emails.
  const cell = v => {
    let s = String(v ?? '');
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  };
  const lines = [['Name', 'Email', 'Temporary Password'].map(cell).join(',')];
  credentials.forEach(c => lines.push([c.name, c.email, c.password].map(cell).join(',')));

  const blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'imported_staff_credentials.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}
