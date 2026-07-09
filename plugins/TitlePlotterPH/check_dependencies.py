import sys
import pkg_resources

def check_package(package_name):
    try:
        version = pkg_resources.get_distribution(package_name).version
        print(f"✓ {package_name} is installed (version {version})")
        return True
    except pkg_resources.DistributionNotFound:
        print(f"✗ {package_name} is NOT installed")
        return False

def main():
    print("Checking required packages for Title Plotter Philippine Land Titles plugin...")
    print("-" * 60)
    
    # Core dependencies
    required_packages = [
        'shapely'
    ]
    
    missing_packages = []
    for package in required_packages:
        if not check_package(package):
            missing_packages.append(package)
    
    print("-" * 60)
    if missing_packages:
        print("\nMissing packages:")
        for package in missing_packages:
            print(f"pip install {package}")
    else:
        print("\nAll required packages are installed!")
    
    print("\nPython version:", sys.version)
    print("Python executable:", sys.executable)

if __name__ == "__main__":
    main() 