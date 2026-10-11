"""Conservative candidate parsing: only values actually present in source text."""
import io
import re
from datetime import datetime
from pypdf import PdfReader

BIOMARKER_PATTERNS = [
    {
        "name": "Fasting Blood Glucose",
        "aliases": [r"fasting\s+blood\s+(?:glucose|sugar)", r"\bfbs\b", r"\bfasting\s+glucose\b"]
    },
    {
        "name": "Postprandial Blood Glucose",
        "aliases": [r"post\s*prandial\s+(?:blood\s+)?(?:glucose|sugar)", r"\bppbs\b", r"\bpp\s+glucose\b"]
    },
    {
        "name": "Random Blood Glucose",
        "aliases": [r"random\s+(?:blood\s+)?(?:glucose|sugar)", r"\brbs\b"]
    },
    {
        "name": "HbA1c",
        "aliases": [r"hba1c", r"glycated\s+hemoglobin", r"glycosylated\s+hemoglobin", r"a1c"]
    },
    {
        "name": "Total Cholesterol",
        "aliases": [r"total\s+cholesterol", r"serum\s+cholesterol"]
    },
    {
        "name": "HDL Cholesterol",
        "aliases": [r"hdl\s+cholesterol", r"\bhdl\b", r"high[- ]density\s+lipoprotein"]
    },
    {
        "name": "LDL Cholesterol",
        "aliases": [r"ldl\s+cholesterol", r"\bldl\b", r"low[- ]density\s+lipoprotein"]
    },
    {
        "name": "Serum Triglycerides",
        "aliases": [r"serum\s+triglycerides", r"triglycerides", r"\btgl\b"]
    },
    {
        "name": "Hemoglobin",
        "aliases": [r"\bhemoglobin\b", r"\bhaemoglobin\b", r"\bhgb\b", r"\bhb\b"]
    },
    {
        "name": "Total Leukocyte Count (WBC)",
        "aliases": [r"total\s+leukocyte\s+count", r"total\s+wbc", r"\bwbc\b", r"white\s+blood\s+cell"]
    },
    {
        "name": "Platelet Count",
        "aliases": [r"platelet\s+count", r"\bplatelets\b"]
    },
    {
        "name": "Serum Creatinine",
        "aliases": [r"serum\s+creatinine", r"\bcreatinine\b"]
    },
    {
        "name": "Blood Urea Nitrogen (BUN)",
        "aliases": [r"blood\s+urea\s+nitrogen", r"\bbun\b"]
    },
    {
        "name": "Blood Urea",
        "aliases": [r"blood\s+urea"]
    },
    {
        "name": "Serum Uric Acid",
        "aliases": [r"uric\s+acid", r"serum\s+uric\s+acid"]
    },
    {
        "name": "Serum Bilirubin (Total)",
        "aliases": [r"total\s+bilirubin", r"bilirubin\s+total"]
    },
    {
        "name": "SGOT / AST",
        "aliases": [r"\bsgot\b", r"\bast\b", r"aspartate\s+aminotransferase"]
    },
    {
        "name": "SGPT / ALT",
        "aliases": [r"\bsgpt\b", r"\balt\b", r"alanine\s+aminotransferase"]
    },
    {
        "name": "Thyroid Stimulating Hormone (TSH)",
        "aliases": [r"tsh", r"thyroid\s+stimulating\s+hormone"]
    }
]


def parse_date(text):
    match = re.search(r'(?:date|dated|collected on|report date)\s*[: ]\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}[- ]+[A-Za-z]{3,9}[- ]+\d{4})', text, re.I)
    if not match:
        return None
    value = match.group(1)
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%d-%b-%Y', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None

def parse_medical_document_text(raw_text, filename=''):
    observations, medications = [], []
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    document_date = parse_date(raw_text)
    for line in lines:
        for biomarker in BIOMARKER_PATTERNS:
            match = next((m for pattern in biomarker['aliases'] if (m := re.search(pattern, line, re.I))), None)
            if not match:
                continue
            tail = line[match.end():]
            value = re.match(r'\s*[:=|]?\s*([+-]?\d+(?:\.\d+)?)\s*(mg/dL|mmol/L|%|g/dL|U/L|uIU/mL|mIU/L|lakhs/cumm|/cumm|10\^9/L)?', tail, re.I)
            if not value:
                continue
            # Reference bounds are parsed after the measured value, never from a built-in range.
            remainder = tail[value.end():]
            bounds = re.search(r'([+-]?\d+(?:\.\d+)?)\s*(?:-|–|to)\s*([+-]?\d+(?:\.\d+)?)', remainder, re.I)
            low, high = (float(bounds[1]), float(bounds[2])) if bounds else (None, None)
            flag = None
            for label, patterns in (('H', r'\[(?:H|HIGH)\]|\((?:H|HIGH)\)|\bflag\s*:\s*H(?:IGH)?\b|\bHIGH\s*$'),
                                    ('L', r'\[(?:L|LOW)\]|\((?:L|LOW)\)|\bflag\s*:\s*L(?:OW)?\b|\bLOW\s*$'),
                                    ('NORMAL', r'\[(?:N|NORMAL)\]|\((?:N|NORMAL)\)|\bflag\s*:\s*NORMAL\b|\bNORMAL\s*$')):
                if re.search(patterns, remainder, re.I):
                    flag = label
                    break
            observations.append(dict(id=f'obs-{len(observations)+1}', test_name=biomarker['name'], value_numeric=float(value[1]), value_text=value[1], unit=value[2], reference_low=low, reference_high=high, source_abnormal_flag=flag, source_text=line, confidence='needs_review', validation_status='needs_review'))
            break
        medication = re.match(r'^(?:\d+[.)]\s*)?(?:tab(?:let)?|cap(?:sule)?|inj(?:ection)?|syr(?:up)?)\.?\s+(.+)$', line, re.I)
        if medication:
            body = medication[1]
            name = re.split(r'\s+-\s+|,|\(', body)[0].strip()
            if not name:
                continue
            strength = re.search(r'\d+(?:\.\d+)?\s*(?:mg|mcg|ml|g)\b', body, re.I)
            frequency = re.search(r'\b(?:OD|BD|BID|TDS|TID|HS|SOS)\b|once daily|twice daily|three times daily', body, re.I)
            duration = re.search(r'\d+\s*(?:days|weeks|months)\b', body, re.I)
            direction = re.split(r'\s+-\s+', body, maxsplit=1)
            medications.append(dict(id=f'med-{len(medications)+1}', medication_name=name[:200], strength=strength[0] if strength else None, generic_name=None, dose_instructions=direction[1] if len(direction)>1 else None, route=None, frequency=frequency[0] if frequency else None, duration=duration[0] if duration else None, prescription_date=document_date, source_text=line, confidence='needs_review', validation_status='needs_review'))
    return dict(document_type='lab_report' if observations else 'prescription' if medications else 'other', document_date=document_date, healthcare_provider=None, practitioner_name=None, observations=observations, medications=medications, unreadable_segments=[] if observations or medications else ['No supported structured records found. Review the source and add records manually.'])

def extract_raw_text_from_file(data, mime_type, filename=''):
    if mime_type != 'application/pdf':
        return ''
    reader = PdfReader(io.BytesIO(data))
    return '\n\n'.join(page.extract_text() or '' for page in reader.pages)
