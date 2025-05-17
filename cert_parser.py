from cryptography import x509
from cryptography.hazmat.backends import default_backend
import hashlib

def parse_certificate(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    try:
        cert = x509.load_der_x509_certificate(data, default_backend())
    except ValueError:
        cert = x509.load_pem_x509_certificate(data, default_backend())

    subject = {attr.oid._name: attr.value for attr in cert.subject}
    hash_sha1 = hashlib.sha1(cert.tbs_certificate_bytes).hexdigest()
    return {
        "organization": subject.get("organizationName", ""),
        "director": subject.get("commonName", ""),
        "surname": subject.get("surname", ""),
        "givenName": subject.get("givenName", ""),
        "inn": subject.get("serialNumber", "").replace("TINUA-", ""),
        "edrpou": subject.get("Unknown OID", "").replace("NTRUA-", ""),
        "valid_from": cert.not_valid_before,
        "valid_to": cert.not_valid_after,
        "sha1": hash_sha1
    }
