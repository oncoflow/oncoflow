import edsnlp
import fitz  # import PyMuPDF...for whatever reason it is called fitz

filepath = ''
docpdf = fitz.open(filepath)  # the file with the text you want to change

# We use some APHP NLP tool

nlp = edsnlp.blank("eds")

# Some text cleaning
nlp.add_pipe("eds.normalizer")

# Various simple rules
nlp.add_pipe(
    "eds_pseudo.simple_rules",
    config={"pattern_keys": ["TEL", "MAIL", "SECU", "PERSON"]},
)

# Address detection
nlp.add_pipe("eds_pseudo.addresses")

# Date detection
nlp.add_pipe("eds_pseudo.dates")

# Contextual rules (requires a dict of info about the patient)
nlp.add_pipe("eds_pseudo.context")

# print(docpdf.get_fonts())
# print(docpdf.extract_font())

for page in docpdf:

    # We need to get the fonts for the new text **NOT WORKING ATM**
    # print(page.get_fonts())
    # print(page.extract_fonts())

    text = page.get_text()

    # Some classicals, knowns and not easily found identifiers, **need to be upgraded**
    classicalidentifiers = [  'NIORT' , 'POITIERS' , 'GEORGES RENON', 'CHU LA MILETRIE', '3C Vienne, Nord Deux-Sèvres' , 'Châtellerault']

    for identifier in classicalidentifiers:
        
        found = page.search_for(identifier)  # list of rectangles where to replace
        for item in found:
            # print(type(item))
            # print(page.get_textbox(item), search_term)
            page.add_redact_annot(item, '' )  # create redaction for text
            page.apply_redactions()  # apply the redaction now
            ""
            page.insert_text(item.bl - (0, 2), 'ANNO', fontsize=9.29688, fontname='helv')

    doctext = nlp(
    text
)
    
    for ent in doctext.ents:
        search_term = str(ent)

        # print(search_term, ent.label_)
        # print(page.get_fonts()[4] if len(page.get_fonts()) >= 4 else None)
        found = page.search_for(search_term)  # list of rectangles where to replace
        for item in found:
            # print(type(item))
            # print(page.get_textbox(item), search_term)
            page.add_redact_annot(item, '' )  # create redaction for text
            page.apply_redactions()  # apply the redaction now
            page.insert_text(item.bl - (0, 2), ent.label_, fontsize=9.29688, fontname='helv')


docpdf.save("sandpit\pdfANNO.pdf")