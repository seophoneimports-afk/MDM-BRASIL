import os
import subprocess
import shutil
import zipfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILDER_DIR = r"C:\Users\seoph\.gemini\antigravity\scratch\android-builder"
PROJECT_DIR = os.path.join(REPO_ROOT, "android", "app")
DIST_DIR = os.path.join(REPO_ROOT, "dist")

JAVA_HOME = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
if os.path.exists(os.path.join(JAVA_HOME, "bin", "javac.exe")):
    JAVAC = os.path.join(JAVA_HOME, "bin", "javac.exe")
    JAVA = os.path.join(JAVA_HOME, "bin", "java.exe")
else:
    JAVAC = "javac"
    JAVA = "java"

AAPT2 = os.path.join(BUILDER_DIR, "aapt2.exe")
ANDROID_JAR = os.path.join(BUILDER_DIR, "android.jar")
R8_JAR = os.path.join(BUILDER_DIR, "r8.jar")
UBER_SIGNER = os.path.join(BUILDER_DIR, "uber-apk-signer.jar")

def run(cmd, cwd=None):
    if isinstance(cmd, str):
        import shlex
        cmd = shlex.split(cmd)
    print("[*] RUN:", " ".join(cmd))
    env = os.environ.copy()
    env["__COMPAT_LAYER"] = "RunAsInvoker"
    res = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, shell=False)
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print("STDERR:", res.stderr)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed with code {res.returncode}")
    return res.stdout

def compile_apk():
    print("=" * 60)
    print("Compiling MDM & FRP BRASIL Device Service APK...")
    print("=" * 60)

    build_dir = os.path.join(PROJECT_DIR, "build")
    gen_dir = os.path.join(PROJECT_DIR, "gen")
    classes_dir = os.path.join(PROJECT_DIR, "classes")
    res_dir = os.path.join(PROJECT_DIR, "res")
    manifest_path = os.path.join(PROJECT_DIR, "AndroidManifest.xml")

    # Clean intermediate build directories (preserve gen_dir which holds R.java)
    for d in [build_dir, classes_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)

    # 1. AAPT2 compile
    print("\n--- 1. AAPT2 Compile Resources ---")
    compiled_res = os.path.join(build_dir, "res.zip")
    run([AAPT2, "compile", "--dir", res_dir, "-o", compiled_res])

    # 2. AAPT2 link
    print("\n--- 2. AAPT2 Link Resources & Manifest ---")
    base_apk = os.path.join(build_dir, "base_unaligned.apk")
    run([
        AAPT2, "link",
        "-I", ANDROID_JAR,
        "--manifest", manifest_path,
        "--min-sdk-version", "24",
        "--target-sdk-version", "34",
        "-o", base_apk,
        "-R", compiled_res,
        "--auto-add-overlay"
    ])
    import time
    for _ in range(30):
        if os.path.exists(base_apk):
            break
        time.sleep(0.3)
    if not os.path.exists(base_apk):
        raise FileNotFoundError(f"Failed to generate base_unaligned.apk at {base_apk}")

    # 3. JAVAC compile
    print("\n--- 3. JAVAC Compile Java Source Code ---")
    java_files = []
    seen = set()
    for search_dir in [PROJECT_DIR, gen_dir]:
        for r, d, files in os.walk(search_dir):
            for file in files:
                if file.endswith(".java"):
                    full_p = os.path.join(r, file)
                    if full_p not in seen:
                        seen.add(full_p)
                        java_files.append(full_p)

    print(f"Compiling {len(java_files)} Java source files...")
    run([
        JAVAC,
        "-encoding", "UTF-8",
        "-source", "8",
        "-target", "8",
        "-cp", ANDROID_JAR,
        "-d", classes_dir,
        *java_files
    ])

    # 4. D8 dex generation
    print("\n--- 4. D8 Convert .class to classes.dex ---")
    class_files = []
    for r, d, files in os.walk(classes_dir):
        for file in files:
            if file.endswith(".class"):
                class_files.append(os.path.join(r, file))

    run([
        JAVA,
        "-cp", R8_JAR,
        "com.android.tools.r8.D8",
        "--lib", ANDROID_JAR,
        "--output", build_dir,
        "--min-api", "26",
        *class_files
    ])

    # 5. Package classes.dex into APK
    print("\n--- 5. Package classes.dex into final_unsigned.apk ---")
    final_unsigned = os.path.join(build_dir, "final_unsigned.apk")
    shutil.copyfile(base_apk, final_unsigned)
    dex_path = os.path.join(build_dir, "classes.dex")

    with zipfile.ZipFile(final_unsigned, "a") as z:
        z.write(dex_path, "classes.dex")

    # 6. Sign and Zipalign with Uber-APK-Signer
    print("\n--- 6. Zipalign and Sign APK ---")
    out_dir = os.path.join(build_dir, "signed_output")
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    run([JAVA, "-jar", UBER_SIGNER, "-a", final_unsigned, "-o", out_dir])

    signed_output = os.path.join(out_dir, "final_unsigned-aligned-debugSigned.apk")
    if not os.path.exists(signed_output):
        raise FileNotFoundError(f"Signed APK not found at {signed_output}")

    # Copy to target distribution paths
    os.makedirs(DIST_DIR, exist_ok=True)
    target_apk = os.path.join(DIST_DIR, "MDM_FRP_BRASIL_DEVICE_SERVICE.apk")
    shutil.copyfile(signed_output, target_apk)

    # Also copy to resources directory for the Windows app to bundle inside EXE
    win_res_dir = os.path.join(REPO_ROOT, "windows", "resources")
    os.makedirs(win_res_dir, exist_ok=True)
    shutil.copyfile(signed_output, os.path.join(win_res_dir, "MDM_FRP_BRASIL_DEVICE_SERVICE.apk"))

    # Copy to server static directory for cloud download
    srv_static_dir = os.path.join(REPO_ROOT, "server", "static")
    os.makedirs(srv_static_dir, exist_ok=True)
    shutil.copyfile(signed_output, os.path.join(srv_static_dir, "MDM_FRP_BRASIL_DEVICE_SERVICE.apk"))

    print("\n" + "=" * 60)
    print(f"[SUCCESS] APK GENERATED: {target_apk}")
    print(f"Size: {os.path.getsize(target_apk)} bytes")
    print("=" * 60)

if __name__ == "__main__":
    compile_apk()
