"""Field names of the Impact receipt page (docs/providers/impact.md §3).

The commercial view marks fields with ``field-<Name>`` CSS classes. The tax view
(myDATA) uses label/value table rows whose labels are Greek in every culture
(observed 2026-11-14). Labels are compared after whitespace collapsing.
"""

# --- Commercial view ------------------------------------------------------------
ADDRESS_FIELDS = frozenset({"Street", "Number", "City", "Postal", "Country"})
# Fields read per section; any other field there is reported in unknown_fields (format drift).
COMMERCIAL_KNOWN = {
    "header": frozenset(
        {
            "RegisteredName",
            "Activities",
            "Vat",
            "TaxOffice",
            "GeneralCommercialRegistryNumber",
            "RegistrationNumber",
            "Phones",
            "Emails",
            "Url",
            "OtherInfo",
            *ADDRESS_FIELDS,
        }
    ),
    "identity": frozenset({"InvoiceType", "IssuerFormatedInvoiceSeriesNumber", "DateIssued"}),
    "line": frozenset(
        {
            "Code",
            "Description1",
            "Quantity",
            "MeasurementUnit",
            "UnitPrice",
            "NetTotal",
            "VatCategory",
            "VATTotal",
            "Total",
        }
    ),
    "payment": frozenset({"PaymentMethodType", "Amount"}),
    "summary": frozenset({"CurrencyCode", "TotalNetAmount", "TotalVATAmount", "TotalGrossValue"}),
    "certification": frozenset({"Mark", "Uid", "ServiceSupplier"}),
}
# Personal or secret values that are never read (the sanitizer replaces them).
COMMERCIAL_DROP = frozenset({"TransactionId", "Authentication"})

# --- Tax view (myDATA) ------------------------------------------------------------
TAX_HEADER = {
    "Σειρά Παραστατικού": "series",
    "ΑΑ Παραστατικού": "number",
    "Ημερομηνία Έκδοσης": "issue_date",
    "Είδος Παραστατικού": "type_code",
    "Νόμισμα": "currency",
    "Ένδειξη Αυτοτιμολόγησης": "self_billing",
}
TAX_ISSUER = {
    "ΑΦΜ": "vat",
    "Κωδ. Χώρας": "country",
    "Αρ. Εγκατάστασης": "branch",
}
ISSUER_PARTY_TITLE = "Στοιχεία Εκδότη"
TAX_SUMMARY = {
    "Σύνολο Καθαρής Αξίας": "net",
    "Σύνολο ΦΠΑ": "vat",
    "Σύνολο Παρ. Φόρων": "withheld",
    "Σύνολο Τελών": "fees",
    "Σύνολο Ψηφιακού Τέλους συναλλαγής": "digital_fee",
    "Σύνολο Λοιπών Φόρων": "other_taxes",
    "Σύνολο Χαρτοσήμου": "stamp_duty",
    "Σύνολο Κρατήσεων": "deductions",
    "Συνολική Αξία": "gross",
}
TAX_PAYMENT = {
    "Τύπος Πληρωμής": "method_code",
    "Αναλογούν Ποσό": "amount",
    "Φιλοδώρημα": "tip",
}
TAX_IDENTIFIERS = {
    "Μοναδικός Αριθμός Καταχώρησης Παραστατικού": "mark",
    "Αναγνωριστικό Παραστατικού": "uid",
    "Url με το οποίο ο λήπτης του παραστατικού θα μπορεί να το λαμβάνει": "url",
    "Μοναδικός Αριθμός Καταχώρησης Ακυρωτικού": "cancellation_mark",
}
# Long labels matched by prefix.
TAX_IDENTIFIER_PREFIXES = {"Αδυναμία Επικοινωνίας Παρόχου": "transmission_failure"}
TAX_LINE = {
    "ΑΑ Γραμμής": "line_number",
    "Είδος Γραμμής": "line_type_code",
    "Κωδικός Είδους": "code",
    "Περιγραφή Είδους": "description",
    "Ποσότητα": "quantity",
    "Είδος Ποσότητας": "unit_code",
    "Επισήμανση": "detail_type",
    "Καθαρή Αξία": "net",
    "Κατηγορία ΦΠΑ": "vat_category",
    "Ποσό ΦΠΑ": "vat",
    "Κατηγορία Αιτίας Εξαίρεσης ΦΠΑ": "vat_exemption",
    "Δικαίωμα Έκπτωσης": "deduction_right",
    "Ποσό Παρ. Φόρου": "withheld",
    "Κατηγορία Συντελεστή Παρ. Φόρου": "withheld_category",
    "Ποσό Ψηφιακού Τέλους συναλλαγής": "digital_fee",
    "Κατηγορία Συντελεστή Ψηφιακού Τέλους συναλλαγής": "digital_fee_category",
    "Ποσό Τελών": "fees",
    "Κατηγορία Συντελεστή Τελών": "fees_category",
    "Ποσό Λοιπών Φόρων": "other_taxes",
    "Κατηγορία Συντελεστή Λοιπών Φόρων": "other_taxes_category",
    "Ποσό Χαρτοσήμου": "stamp_duty",
    "Ποσό Φόρου Διαμονής": "accommodation_tax",
    "Ποσό Κρατήσεων": "deductions",
    "Σχόλια Γραμμής": "comments",
    "Ένδειξη μη συμμετοχής στο ΦΠΑ (έσοδα – εκροές)": "not_vat_relevant",
}
# Personal or secret values: skipped, never stored (the sanitizer replaces them).
TAX_DROP = frozenset(
    {
        "Μοναδική Ταυτότητα Πληρωμής",
        "ID Τερματικού POS",
        "Provider’s Id",
        "Provider's Id",
        "Υπογραφή",
        "Συμβολοσειρά Αυθεντικοποίησης Παρόχου",
    }
)

NOT_FOUND_MARKER = "Document with UniqueId"
