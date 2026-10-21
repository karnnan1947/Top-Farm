"""Open the report in Word, update the table of contents and page fields, save it and export the PDF."""
import os
import sys

import win32com.client

docx = os.path.abspath(sys.argv[1])
pdf = os.path.splitext(docx)[0] + '.pdf'
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
try:
    doc = word.Documents.Open(docx, ReadOnly=False, AddToRecentFiles=False)
    for toc in doc.TablesOfContents:
        toc.Update()
    doc.Fields.Update()
    doc.Repaginate()
    for toc in doc.TablesOfContents:
        toc.UpdatePageNumbers()
    doc.Save()
    doc.ExportAsFixedFormat(pdf, 17, OpenAfterExport=False, OptimizeFor=0, CreateBookmarks=1)  # 17 = PDF
    print('pages:', doc.ComputeStatistics(2), '| pdf:', pdf)
    doc.Close(False)
finally:
    word.Quit()
