import zipfile

def extract_zip(file_path, extract_to):
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

def is_certificate_file(filename):
    return filename.lower().endswith(('.cer', '.crt', '.pem'))
