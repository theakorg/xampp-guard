#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, ctypes, subprocess, shutil, time, datetime, uuid, random, threading, tempfile, zipfile
from pathlib import Path
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil as _termshutil  # for terminal width

# ── Config ─────────────────────────────────────────────────────────────────────
SYSTEM_DBS = {"information_schema","mysql","performance_schema","sys"}

# ANSI Colors (Fallback Safe)
try:
    import colorama
    colorama.just_fix_windows_console()
    HAS_COLOR = True
except Exception:
    HAS_COLOR = sys.stdout.isatty()

def c(s, code): return f"\033[{code}m{s}\033[0m" if HAS_COLOR else s
C_ACCENT="38;5;208"; C_TITLE="38;5;45"; C_SUBTITLE="38;5;250"; C_OK="38;5;40"; C_WARN="38;5;214"; C_ERR="38;5;196"; C_DIM="2"

def title_case(t): return " ".join(w[:1].upper()+w[1:] for w in t.split())

# ── UUIDv7-Custom: first/last char are letters ─────────────────────────────────
def uuid7_custom() -> str:
    def letter(): return random.choice("abcdef")
    unix_ms = int(time.time()*1000)
    th = (unix_ms>>28)&0xFFFF
    tm = (unix_ms>>12)&0xFFFF
    tl = (unix_ms & 0xFFF) | (7<<12)
    ra = uuid.uuid4().int >> 64
    rb = uuid.uuid4().int & ((1<<62)-1)
    rb |= 0x8000000000000000
    s = f"{th:04x}{tm:04x}-{tl:04x}-{(ra>>48)&0xFFFF:04x}-{(ra>>32)&0xFFFF:04x}-{rb:016x}"
    L=list(s)
    if L[0].isdigit():  L[0]=letter()
    if L[-1].isdigit(): L[-1]=letter()
    return "".join(L)

# ── Admin ──────────────────────────────────────────────────────────────────────
def is_admin()->bool:
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception: return False

def elevate_if_needed():
    if not is_admin():
        try:
            params=" ".join(['"{}"'.format(a) if " " in a else a for a in sys.argv])
            rc=ctypes.windll.shell32.ShellExecuteW(None,"runas",sys.executable,params,None,1)
            if rc>32: sys.exit(0)
        except Exception: pass

# ── Shell Helpers ──────────────────────────────────────────────────────────────
def run_text(cmd: List[str], timeout:int=None)->Tuple[int,str,str]:
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace",timeout=timeout)
        return p.returncode,p.stdout,p.stderr
    except Exception as e:
        return 1,"",str(e)

def exe(bin_dir: Path, name:str)->str: return str(bin_dir/name)
def ask(prompt:str, default:str="")->str:
    s=input(c(title_case(prompt),C_SUBTITLE)+" ").strip(); return s if s else default

def prompt_drive(default="C")->str:
    while True:
        d=ask(f"Enter XAMPP Drive Letter [{default}]:", default).upper()
        if len(d)==2 and d[1]==":": d=d[0]
        if len(d)==1 and d.isalpha(): return d
        print(c("Please Enter A Single Drive Letter (e.g., C or D).",C_WARN))

def ensure_dir(p:Path): p.mkdir(parents=True,exist_ok=True)

def wait_for_tcp(host:str, port:int, timeout_s:int=25)->bool:
    import socket
    t0=time.time()
    while time.time()-t0<timeout_s:
        try:
            with socket.create_connection((host,port),timeout=1): return True
        except Exception: time.sleep(1)
    return False

# ── MySQL Helpers ──────────────────────────────────────────────────────────────
def get_dbs_via_server(mysql_exe:str, host:str, port:int, user:str, pwd:str)->Tuple[bool,List[str],str]:
    cmd=[mysql_exe,"-h",host,"-P",str(port),"-u",user,"-N","-e","SHOW DATABASES"]
    if pwd: cmd.append(f"-p{pwd}")
    rc,out,err=run_text(cmd)
    if rc==0:
        return True,[x.strip() for x in out.splitlines() if x.strip()], ""
    return False,[], (err or out or f"Mysql Exit {rc}")

def start_mysqld_temp(bin_dir:Path, xampp_dir:Path, datadir:Path, port:int=3306):
    ini=xampp_dir/"mysql"/"bin"/"tmp_recovery.ini"
    ini.write_text(
        "[mysqld]\n"
        f"basedir={str(xampp_dir/'mysql').replace('\\','/')}\n"
        f"datadir={str(datadir).replace('\\','/')}\n"
        f"port={port}\n"
        f"socket={str(xampp_dir/'mysql'/'mysql.sock').replace('\\','/')}\n"
        "innodb_force_recovery=6\n"
        "innodb_purge_threads=0\n"
        "innodb_doublewrite=0\n"
        "innodb_log_checksums=ON\n"
        "innodb_checksum_algorithm=crc32\n",encoding="ascii"
    )
    mysqld=exe(bin_dir,"mysqld.exe")
    try:
        proc=subprocess.Popen([mysqld,f"--defaults-file={ini}","--standalone","--console"],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except Exception:
        return False,None,ini
    if wait_for_tcp("127.0.0.1",port,25): return True,proc,ini
    return False,proc,ini

def stop_process(proc):
    try:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
    except Exception: pass

def mysqldump_to_file(bin_dir:Path, host:str, port:int, user:str, pwd:str, db:str, out_path:Path):
    cmd=[exe(bin_dir,"mysqldump.exe"),"-h",host,"-P",str(port),"-u",user,db,
         "--routines","--events","--triggers","--single-transaction","--skip-lock-tables",
         "--default-character-set=utf8mb4", f"--result-file={str(out_path)}"]
    if pwd: cmd.insert(3,f"-p{pwd}")
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace")
        return p.returncode,p.stdout,p.stderr
    except Exception as e:
        return 1,"",str(e)

# ── UI / ASCII ─────────────────────────────────────────────────────────────────
SPIN=["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

ASCII_LOGO = r"""__  ______ _   _   _    ____  ____  
\ \/ / ___| | | | / \  |  _ \|  _ \ 
 \  / |  _| | | |/ _ \ | |_) | | | |
 /  \ |_| | |_| / ___ \|  _ <| |_| |
/_/\_\____|\___/_/   \_\_| \_\____/ XAMPPGUARD"""

def term_width(min_w=50, max_w=240) -> int:
    try:
        w = _termshutil.get_terminal_size((100, 25)).columns
    except Exception:
        w = 100
    return max(min_w, min(w, max_w))

def center_line(txt: str) -> str:
    w = term_width()
    return txt.center(w) if len(txt) < w else txt[:w]

def hline(ch="═") -> str:
    return ch * term_width()

def SEP():
    return c(hline("─"), C_SUBTITLE)

def clear(): os.system("cls" if os.name=="nt" else "Clear")

def banner(center_text: str | None = None):
    """Logo Left; Optional Centered Title. If Center_Text Is None, Do NOT Print Extra Lines."""
    clear()
    # Logo (left-aligned)
    for line in ASCII_LOGO.splitlines():
        print(c(line, C_TITLE))
    if center_text:
        print(c(hline("═"), C_SUBTITLE))
        print(c(center_line(center_text), C_ACCENT))
        print(c(hline("═"), C_SUBTITLE))

def header_center(title: str):
    print(c(hline("─"), C_SUBTITLE))
    print(c(center_line(title_case(title)), C_ACCENT))
    print(c(hline("─"), C_SUBTITLE))

def render_progress(done:int,total:int,w:int=40,spin_idx:int=0,prefix:str=""):
    r=0 if total==0 else done/total
    bar="█"*int(w*r)+"░"*(w-int(w*r))
    pct=f"{int(r*100):3d}%"
    spin=SPIN[spin_idx%len(SPIN)]
    line=(prefix+" " if prefix else "")+f"[ {bar} ] {pct}  {done}/{total}  {spin}"
    print("\r"+c(line,C_SUBTITLE),end="",flush=True)

def print_kv(key:str, val:str, val_color=C_SUBTITLE):
    k=c(title_case(key).ljust(14), C_DIM); v=c(val, val_color); print(f"{k} {v}")

# ── ZIP With Progress For Directories ──────────────────────────────────────────
def count_files(root: Path, exclude_pred=None) -> int:
    total=0
    for base, dirs, files in os.walk(root):
        base_path = Path(base)
        if exclude_pred and exclude_pred(base_path):
            dirs[:] = []
            continue
        total += len(files)
    return total

def zip_tree_with_progress(src_root: Path, zip_path: Path, exclude_pred=None):
    total = count_files(src_root, exclude_pred)
    done = 0; spin=0
    render_progress(done,total,spin_idx=spin,prefix="Packing")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for base, dirs, files in os.walk(src_root):
            base_path = Path(base)
            if exclude_pred and exclude_pred(base_path):
                dirs[:] = []
                continue
            for name in files:
                fp = base_path / name
                try:
                    arcname = str(fp.relative_to(src_root))
                    zf.write(fp, arcname)
                except Exception:
                    pass
                done += 1; spin += 1
                render_progress(done,total,spin_idx=spin,prefix="Packing")
    print()

# ── Option 1: Core Backup (XAMPP Folder) ───────────────────────────────────────
def core_backup_xampp():
    banner(None)  # no centered "XAMPP GUARD" or extra lines here
    header_center("Core Backup (XAMPP Folder)")
    elevate_if_needed()

    drive = prompt_drive("C")
    xampp_dir = Path(f"{drive}:/xampp")

    now=datetime.datetime.now()
    uuid_str = uuid7_custom()
    out_dir = xampp_dir/"guard"/"backup"/"core"/f"{now.year:04d}"/f"{now.month:02d}"/f"{now.day:02d}"
    ensure_dir(out_dir)
    zip_path = out_dir / f"{uuid_str.replace('-','')}.zip"

    header_center("Paths")
    print_kv("XAMPP Dir", str(xampp_dir))
    print_kv("Zip Output", str(zip_path))
    print()

    if not xampp_dir.exists():
        print(c("XAMPP Folder Not Found.", C_ERR))
        input(c("Press Enter To Return To Menu...", C_SUBTITLE)); return

    # Exclude guard/backup subtree
    guard_backup = (xampp_dir/"guard"/"backup").resolve()
    def exclude_pred(p: Path):
        try:
            return str(p.resolve()).startswith(str(guard_backup))
        except Exception:
            return False

    header_center("Collecting")
    zip_tree_with_progress(xampp_dir, zip_path, exclude_pred=exclude_pred)

    header_center("Summary")
    print_kv("Zip Output",    str(zip_path), C_ACCENT)
    print(); input(c("Press Enter To Return To Menu...", C_SUBTITLE))

# ── Option 2: Database Backup (ZIP-Only; Temp Workspace) ───────────────────────
def database_backup_zip_only():
    banner(None)  # only logo
    header_center("Database Backup (XAMPP/MariaDB)")
    elevate_if_needed()

    drive=prompt_drive("C")
    xampp_dir=Path(f"{drive}:/xampp")
    bin_dir  =xampp_dir/"mysql"/"bin"
    data_dir =xampp_dir/"mysql"/"data"

    now=datetime.datetime.now()
    uuid_str=uuid7_custom()
    out_dir = xampp_dir/"guard"/"backup"/"database"/f"{now.year:04d}"/f"{now.month:02d}"/f"{now.day:02d}"
    ensure_dir(out_dir)
    zip_path = out_dir/f"{uuid_str.replace('-','')}.zip"

    header_center("Paths")
    print_kv("XAMPP Dir", str(xampp_dir))
    print_kv("MySQL Bin", str(bin_dir))
    print_kv("Data Dir",  str(data_dir))
    print_kv("Zip Output", str(zip_path))
    print()

    if not bin_dir.exists():
        print(c("MySQL Bin Folder Not Found. Check Your XAMPP Installation.", C_ERR))
        input(c("Press Enter To Return To Menu...", C_SUBTITLE)); return

    host,port,user="127.0.0.1",3306,"root"
    yn = ask("Does MySQL User 'root' Have A Password? (Y/N):","N").lower()
    pwd= ask("Enter password:") if yn.startswith("y") else ""

    # Temp workspace
    temp_root = Path(tempfile.mkdtemp(prefix="xguard_db_"))
    log_path = temp_root/"backup.log"
    log_lock=threading.Lock()
    def log(msg:str):
        with log_lock:
            with open(log_path,"a",encoding="utf-8") as f: f.write(msg+"\n")

    header_center("Connection")
    ok,dbs,err = get_dbs_via_server(exe(bin_dir,"mysql.exe"),host,port,user,pwd)
    proc=None; ini_path=None

    if not ok:
        print(c("Could Not Connect. Starting Temporary Recovery Mode...", C_WARN))
        started,proc,ini_path = start_mysqld_temp(bin_dir,xampp_dir,data_dir,port)
        if started:
            print(c("MySQL started in recovery mode.", C_OK))
            ok,dbs,err = get_dbs_via_server(exe(bin_dir,"mysql.exe"),host,port,user,pwd)
        else:
            print(c("Failed To Start MySQL. Falling Back To Cold Copy.", C_WARN))
            cold_root = temp_root/"cold_copy"
            cold_root.mkdir(parents=True, exist_ok=True)
            schemas = [p.name for p in data_dir.iterdir() if p.is_dir() and p.name not in SYSTEM_DBS]
            total=len(schemas); done=0; spin=0
            header_center("Cold Copy")
            render_progress(done,total,spin_idx=spin,prefix="Copy")
            successes: List[str] = []
            errors: List[Tuple[str,str]] = []
            for d in schemas:
                try:
                    dst = cold_root/d; dst.mkdir(parents=True, exist_ok=True)
                    src = data_dir/d
                    for item in src.iterdir():
                        if item.is_file() and item.suffix.lower() in (".frm",".ibd",".cfg",".par",".ibz",".myd",".myi"):
                            shutil.copy2(str(item), str(dst/item.name))
                    log(f"OK (Cold): {d}"); successes.append(d)
                except Exception as e:
                    msg=str(e); errors.append((d,msg)); log(f"FAIL (Cold): {d}: {msg}")
                done+=1; spin+=1; render_progress(done,total,spin_idx=spin,prefix="Copy")
            print()
            header_center("Packing Zip")
            shutil.make_archive(str(zip_path.with_suffix("")),"zip",root_dir=str(temp_root))
            if proc: stop_process(proc)
            if ini_path and ini_path.exists():
                try: ini_path.unlink()
                except Exception: pass
            shutil.rmtree(temp_root, ignore_errors=True)
            header_center("Summary")
            print_kv("Success", str(len(successes)), C_OK)
            print_kv("Errors",  str(len(errors)),   C_ERR)
            if successes:
                print(c("\nSuccess:", C_OK))
                for d in sorted(successes): print("  •", d)
            if errors:
                print(c("\nErrors:", C_ERR))
                for d,m in errors: print(f"  • {d}: {m}")
            print_kv("Zip Output", str(zip_path), C_ACCENT)
            print(); input(c("Press Enter To Return To Menu...", C_SUBTITLE)); return

    user_dbs=[d for d in dbs if d not in SYSTEM_DBS]
    if not user_dbs:
        print(c("No user databases found.", C_WARN))
        shutil.rmtree(temp_root, ignore_errors=True)
        input(c("Press Enter To Return To Menu...", C_SUBTITLE)); return

    header_center("Backup")
    print(c(f"Backing Up {len(user_dbs)} Database(s) In Background...", C_SUBTITLE))
    total=len(user_dbs); done=0; spin=0
    render_progress(done,total,spin_idx=spin,prefix="Dump")

    successes: List[str] = []
    errors: List[Tuple[str,str]] = []

    def worker(dbname:str):
        out_sql = temp_root / f"{dbname}.sql"
        rc,out,err = mysqldump_to_file(bin_dir,host,port,user,pwd,dbname,out_sql)
        if rc==0 and out_sql.exists() and out_sql.stat().st_size>0:
            log(f"OK: {dbname}")
            return (dbname,True,"")
        else:
            msg=err or out or f"exit {rc}"
            log(f"FAIL: {dbname}: {msg}")
            return (dbname,False,msg)

    max_workers=min(3,max(1,os.cpu_count() or 2))
    lock=threading.Lock()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs={ex.submit(worker,db):db for db in user_dbs}
        for fut in as_completed(futs):
            name,ok,msg=fut.result()
            with lock:
                if ok: successes.append(name)
                else:  errors.append((name,msg))
                done+=1; spin+=1; render_progress(done,total,spin_idx=spin,prefix="Dump")
    print()

    if proc: stop_process(proc)
    if ini_path and ini_path.exists():
        try: ini_path.unlink()
        except Exception: pass

    header_center("Packing Zip")
    shutil.make_archive(str(zip_path.with_suffix("")),"zip",root_dir=str(temp_root))
    shutil.rmtree(temp_root, ignore_errors=True)

    header_center("Summary")
    print_kv("Success", str(len(successes)), C_OK)
    print_kv("Errors",  str(len(errors)),   C_ERR)
    if successes:
        print(c("\nSuccess:", C_OK))
        for n in sorted(successes): print("  •", n)
    if errors:
        print(c("\nErrors:", C_ERR))
        for n,m in errors: print(f"  • {n}: {m}")
    print_kv("Zip Output", str(zip_path), C_ACCENT)
    print(); input(c("Press Enter To Return To Menu...", C_SUBTITLE))

# ── Option 3: Web Root Backup (htdocs) ─────────────────────────────────────────
def webroot_backup_htdocs():
    banner(None)  # only logo
    header_center("Web Root Backup (htdocs)")
    elevate_if_needed()

    drive = prompt_drive("C")
    xampp_dir = Path(f"{drive}:/xampp")
    htdocs = xampp_dir/"htdocs"

    if not htdocs.exists():
        print(c("htdocs Folder Not Found.", C_ERR))
        input(c("Press Enter To Return To Menu...", C_SUBTITLE)); return

    now=datetime.datetime.now()
    uuid_str = uuid7_custom()
    out_dir = xampp_dir/"guard"/"backup"/"htdocs"/f"{now.year:04d}"/f"{now.month:02d}"/f"{now.day:02d}"
    ensure_dir(out_dir)
    zip_path = out_dir/f"{uuid_str.replace('-','')}.zip"

    header_center("Paths")
    print_kv("Web Root",  str(htdocs))
    print_kv("Zip Output", str(zip_path))
    print()

    header_center("Collecting")
    def exclude_none(p: Path): return False
    zip_tree_with_progress(htdocs, zip_path, exclude_pred=exclude_none)

    header_center("Summary")
    print_kv("Zip Output",    str(zip_path), C_ACCENT)
    print(); input(c("Press Enter To Return To Menu...", C_SUBTITLE))

# ── Menu ───────────────────────────────────────────────────────────────────────
def main_menu():
    while True:
        banner("XAMPP GUARD")  # only main menu shows centered menu title
        print(c("1) Core Backup :: XAMPP Folder (Zip Only)", C_ACCENT))
        print(c("2) Database :: Backup (XAMPP/MariaDB) (Zip Only)", C_ACCENT))
        print(c("3) Web Root :: Backup (htdocs) (Zip Only)", C_ACCENT))
        print(c("4) Exit", C_ACCENT))
        print(SEP())
        choice = ask("Select an option [1-4]:", "1")
        if choice == "1":
            core_backup_xampp()
        elif choice == "2":
            database_backup_zip_only()
        elif choice == "3":
            webroot_backup_htdocs()
        elif choice == "4":
            print(c("Goodbye!", C_TITLE)); return
        else:
            print(c("Unknown choice.", C_WARN)); time.sleep(1.0)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print(); print(c("Interrupted.", C_WARN))
