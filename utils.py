import zipfile

def extract_zip(file_path, extract_to):
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
    except zipfile.BadZipFile:
        raise Exception("Файл не является корректным ZIP архивом")
    except zipfile.LargeZipFile:
        raise Exception("ZIP архив слишком большой")
    except Exception as e:
        raise Exception(f"Ошибка при распаковке архива: {e}")

def is_certificate_file(filename):
    return filename.lower().endswith(('.cer', '.crt', '.pem'))
