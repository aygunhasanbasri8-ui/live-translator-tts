# Mutlak import: PyInstaller bu dosyayı paket dışında, düz betik olarak
# çalıştırıyor; göreli import exe'yi açılışta düşürüyordu.
from live_translator import main

if __name__ == "__main__":
    raise SystemExit(main())
