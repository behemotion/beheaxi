"""A deliberately non-compliant CLI used to prove the conformance runner catches failures."""
import sys

if __name__ == "__main__":
    print("not a manifest")
    sys.exit(0)
