import streamlit as st
import sqlite3
import os
from pathlib import Path
from datetime import date, datetime, timedelta
import calendar
import uuid
import html
import requests

# ============================================================
# 해야지 - 학교/과제 일정 관리 앱
# ============================================================

st.set_page_config(
    page_title="해야지",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE = Path(__file__).parent
DB_PATH = BASE / "haeyaji.db"
UPLOAD_DIR = BASE / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# -----------------------------
# DB
# -----------------------------
def db():
    # SQLite 동시성 예외 방지를 위해 check_same_thread 옵션 추가
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        task_type TEXT NOT NULL DEFAULT '일반 과제',
        subject TEXT NOT NULL DEFAULT '',
        start_date TEXT NOT NULL,
        deadline TEXT NOT NULL,
        guide TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        special_alarm_note TEXT DEFAULT '',
        duration_type TEXT NOT NULL DEFAULT '일반',
        progress INTEGER NOT NULL DEFAULT 0,
        alarm_enabled INTEGER NOT NULL DEFAULT 0,
        alarm_days_before INTEGER NOT NULL DEFAULT 1,
        alarm_time TEXT NOT NULL DEFAULT '18:00',
        submission_checked INTEGER NOT NULL DEFAULT 0,
        materials TEXT DEFAULT '',
        materials_checked INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS task_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        original_name TEXT NOT NULL,
        saved_path TEXT NOT NULL,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS task_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS school_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        event_date TEXT NOT NULL,
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS archives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT DEFAULT '',
        link TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS archive_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        archive_id INTEGER NOT NULL,
        original_name TEXT NOT NULL,
        saved_path TEXT NOT NULL,
        FOREIGN KEY(archive_id) REFERENCES archives(id)
    )
    """)

    # NEIS 학교 설정 영구 보존을 위한 테이블
    c.execute("""
    CREATE TABLE IF NOT EXISTS school_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        school_name TEXT NOT NULL,
        school_code TEXT NOT NULL,
        office_code TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


init_db()


def migrate_task_notes():
    conn = db()
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN subject TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass
        
    conn.execute("""
        UPDATE tasks
        SET notes = CASE
            WHEN COALESCE(notes, '') = '' THEN COALESCE(special_alarm_note, '')
            ELSE notes
        END
        WHERE COALESCE(special_alarm_note, '') <> ''
    """)
    conn.commit()
    conn.close()

migrate_task_notes()


# -----------------------------
# Session & Navigation
# -----------------------------
defaults = {
    "page": "home",
    "task_id": None,
    "archive_id": None,
    "year": date.today().year,
    "month": date.today().month,
    "show_school": True,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def navigate(page, task_id=None, archive_id=None):
    st.session_state.page = page
    st.session_state.task_id = task_id
    st.session_state.archive_id = archive_id
    st.rerun()


# -----------------------------
# NEIS & School Config
# -----------------------------
def get_saved_school_config():
    conn = db()
    row = conn.execute("SELECT * FROM school_config WHERE id = 1").fetchone()
    conn.close()
    if row:
        return {
            "name": row["school_name"],
            "code": row["school_code"],
            "office": row["office_code"],
        }
    return None


def save_school_config(name, code, office):
    conn = db()
    conn.execute("""
        INSERT INTO school_config (id, school_name, school_code, office_code)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            school_name=excluded.school_name,
            school_code=excluded.school_code,
            office_code=excluded.office_code
    """, (name, code, office))
    conn.commit()
    conn.close()


def neis_api_key():
    try:
        return st.secrets["NEIS_API_KEY"]
    except Exception:
        return os.getenv("NEIS_API_KEY", "")


def neis_fetch(endpoint, params):
    key = neis_api_key()
    if not key:
        return None, "NEIS_API_KEY가 설정되지 않았습니다."

    base = "https://open.neis.go.kr/hub/" + endpoint
    params = dict(params)
    params.update({"KEY": key, "Type": "json", "pIndex": 1, "pSize": 1000})

    try:
        r = requests.get(base, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data, None
    except requests.exceptions.RequestException as e:
        return None, f"나이스 API 네트워크 통신 오류: {e}"
    except Exception as e:
        return None, f"나이스 API 응답 처리 중 오류 발생: {e}"


def neis_school_search(school_name, education_office):
    data, err = neis_fetch(
        "schoolInfo",
        {
            "ATPT_OFCDC_SC_CODE": education_office,
            "SCHUL_NM": school_name.strip(),
        },
    )
    if err:
        return [], err

    rows = []
    try:
        for block in data.get("schoolInfo", []):
            for row in block.get("row", []):
                rows.append(row)
    except Exception:
        pass
    return rows, None


def neis_calendar(school_code, education_office, from_date, to_date):
    data, err = neis_fetch(
        "SchoolSchedule",
        {
            "ATPT_OFCDC_SC_CODE": education_office,
            "SD_SCHUL_CODE": school_code,
            "AA_FROM_YMD": from_date.strftime("%Y%m%d"),
            "AA_TO_YMD": to_date.strftime("%Y%m%d"),
        },
    )
    if err:
        return [], err

    rows = []
    try:
        for block in data.get("SchoolSchedule", []):
            for row in block.get("row", []):
                rows.append(row)
    except Exception:
        pass
    return rows, None


# -----------------------------
# Helpers
# -----------------------------
def save_uploaded_files(uploaded_files, folder_prefix):
    saved = []
    if not uploaded_files:
        return saved

    folder = UPLOAD_DIR / folder_prefix
    folder.mkdir(exist_ok=True)

    for f in uploaded_files:
        safe_name = Path(f.name).name
        # 안전한 파일 저장을 위해 인코딩/파일명 변환 적용
        unique_prefix = uuid.uuid4().hex
        filename = f"{unique_prefix}_{safe_name}"
        path = folder / filename
        path.write_bytes(f.getbuffer())
        saved.append((safe_name, str(path)))
    return saved


def normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def get_tasks():
    conn = db()
    rows = conn.execute("SELECT * FROM tasks ORDER BY deadline, id").fetchall()
    conn.close()
    return rows


def get_task(task_id):
    conn = db()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return row


def get_task_files(task_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM task_files WHERE task_id=? ORDER BY id", (task_id,)
    ).fetchall()
    conn.close()
    return rows


def get_task_links(task_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM task_links WHERE task_id=? ORDER BY id", (task_id,)
    ).fetchall()
    conn.close()
    return rows


def get_school_events(year=None, month=None):
    conn = db()
    if year and month:
        prefix = f"{year:04d}-{month:02d}"
        rows = conn.execute(
            "SELECT * FROM school_events WHERE substr(event_date,1,7)=? ORDER BY event_date, id",
            (prefix,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM school_events ORDER BY event_date, id"
        ).fetchall()
    conn.close()
    return rows


def get_archives(category="전체", search=""):
    conn = db()
    if category == "전체":
        rows = conn.execute(
            "SELECT * FROM archives ORDER BY created_at DESC, id DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM archives WHERE category=? ORDER BY created_at DESC, id DESC",
            (category,),
        ).fetchall()
    conn.close()

    if search.strip():
        q = search.strip().lower()
        rows = [
            r for r in rows
            if q in (r["title"] or "").lower()
            or q in (r["content"] or "").lower()
        ]
    return rows


def get_archive(archive_id):
    conn = db()
    row = conn.execute(
        "SELECT * FROM archives WHERE id=?", (archive_id,)
    ).fetchone()
    conn.close()
    return row


def get_archive_files(archive_id):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM archive_files WHERE archive_id=? ORDER BY id",
        (archive_id,),
    ).fetchall()
    conn.close()
    return rows


def task_alarm_date(task):
    return date.fromisoformat(task["deadline"]) - timedelta(
        days=int(task["alarm_days_before"])
    )


def today_alarms():
    today = date.today()
    result = []
    for task in get_tasks():
        if not task["alarm_enabled"]:
            continue
        if task_alarm_date(task) == today and task["progress"] < 100:
            result.append(task)
    return result


def school_event_map(year, month):
    result = {}
    for e in get_school_events(year, month):
        result.setdefault(e["event_date"], []).append(e)
    return result


# -----------------------------
# CSS & Layout
# -----------------------------
st.markdown("""
<style>
.block-container {max-width: 1250px; padding-top: 1.5rem;}
.app-title {font-size: 44px; font-weight: 800; text-align:center; margin-top: 12vh;}
.app-subtitle {text-align:center; color:#777; font-size:18px; margin-bottom:35px;}
.daybox {border:1px solid #e6e6e6; border-radius:10px; padding:7px; min-height:125px; background:#fff;}
.daynum {font-weight:700; margin-bottom:5px;}
.task-pill {background:#edf3ff; border-radius:7px; padding:5px 6px; margin:4px 0; font-size:12px;}
.school-pill {background:#fff3cd; border-radius:7px; padding:5px 6px; margin:4px 0; font-size:12px;}
.small-muted {color:#777; font-size:13px;}
.card {border:1px solid #e6e6e6; border-radius:12px; padding:14px; background:white; margin-bottom:10px;}
</style>
""", unsafe_allow_html=True)


def top_nav():
    c1, c2, c3 = st.columns([2.3, 1, 1])
    with c1:
        if st.button("📚 해야지", key="nav_home"):
            navigate("calendar")
    with c2:
        if st.button("📂 이전 과제 / 구상", use_container_width=True):
            navigate("archive")
    with c3:
        if st.button("＋ 테스크", use_container_width=True):
            navigate("add_task")
    st.divider()


# -----------------------------
# Home & Alarms
# -----------------------------
def page_home():
    st.markdown('<div class="app-title">📚 해야지</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="app-subtitle">해야 할 일을 잊지 않도록 한눈에 관리해요.</div>',
        unsafe_allow_html=True
    )
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        if st.button("🚀 시작하기", type="primary", use_container_width=True):
            navigate("calendar")


def alarm_banner():
    alarms = today_alarms()
    if not alarms:
        return

    st.warning("🔔 오늘 확인할 알람이 있어요.")
    for task in alarms:
        checks = []
        if task["submission_checked"]:
            checks.append("제출 확인 완료")
        else:
            checks.append("제출 확인 필요")
        if task["materials"]:
            checks.append(
                "준비물 확인 완료" if task["materials_checked"]
                else "준비물 확인 필요"
            )

        st.info(
            f"**{task['name']}** · 마감 {task['deadline']} · "
            f"진행률 {task['progress']}%\n\n"
            f"알람 시간: {task['alarm_time']} · " + " / ".join(checks) +
            (f"\n\n특이사항: {task['notes']}"
             if task["notes"] else "")
        )


# -----------------------------
# Calendar
# -----------------------------
def page_calendar():
    top_nav()
    st.title("📅 캘린더")

    st.subheader("빠르게 추가하기")
    qa1, qa2, qa3 = st.columns(3)
    with qa1:
        if st.button("＋ 테스크 추가", type="primary", use_container_width=True):
            navigate("add_task")
    with qa2:
        if st.button("＋ 이전 과제 추가", use_container_width=True):
            st.session_state["prefill_archive_category"] = "이전 과제"
            navigate("add_archive")
    with qa3:
        if st.button("＋ 구상 내용 추가", use_container_width=True):
            st.session_state["prefill_archive_category"] = "구상 내용"
            navigate("add_archive")

    alarm_banner()

    a, b, c = st.columns([1, 4, 1])
    with a:
        if st.button("◀ 이전 달", use_container_width=True):
            if st.session_state.month == 1:
                st.session_state.month = 12
                st.session_state.year -= 1
            else:
                st.session_state.month -= 1
            st.rerun()
    with b:
        st.markdown(
            f"<h2 style='text-align:center'>{st.session_state.year}년 "
            f"{st.session_state.month}월</h2>",
            unsafe_allow_html=True,
        )
    with c:
        if st.button("다음 달 ▶", use_container_width=True):
            if st.session_state.month == 12:
                st.session_state.month = 1
                st.session_state.year += 1
            else:
                st.session_state.month += 1
            st.rerun()

    s1, s2, s3 = st.columns([1, 1, 4])
    with s1:
        st.session_state.show_school = st.checkbox(
            "🏫 학사일정 표시",
            value=st.session_state.show_school,
        )
    with s2:
        if st.button("🏫 실제 학사일정 설정"):
            navigate("neis_schedule")

    saved_neis = get_saved_school_config()
    neis_month_events = {}
    if saved_neis and st.session_state.show_school:
        first_day = date(st.session_state.year, st.session_state.month, 1)
        last_day = date(
            st.session_state.year,
            st.session_state.month,
            calendar.monthrange(
                st.session_state.year,
                st.session_state.month
            )[1],
        )
        rows, _ = neis_calendar(
            saved_neis["code"],
            saved_neis["office"],
            first_day,
            last_day,
        )
        for row in rows:
            d = row.get("AA_YMD", "")
            if len(d) == 8:
                d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            neis_month_events.setdefault(d, []).append(row)

    y, m = st.session_state.year, st.session_state.month
    tasks = get_tasks()
    events = school_event_map(y, m)

    task_by_date = {}
    for t in tasks:
        task_by_date.setdefault(t["deadline"], []).append(t)

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(y, m)

    header = st.columns(7)
    for i, name in enumerate(["월", "화", "수", "목", "금", "토", "일"]):
        header[i].markdown(
            f"<div style='text-align:center;font-weight:700'>{name}</div>",
            unsafe_allow_html=True
        )

    for week_idx, week in enumerate(weeks):
        cols = st.columns(7)
        for col_idx, day in enumerate(week):
            with cols[col_idx]:
                if day == 0:
                    st.markdown(
                        "<div class='daybox'></div>", unsafe_allow_html=True
                    )
                    continue

                ds = date(y, m, day).isoformat()
                with st.container(border=True):
                    st.markdown(f"<div class='daynum'>{day}</div>", unsafe_allow_html=True)

                    for t in task_by_date.get(ds, []):
                        label = f"📌 {t['name'][:16]}"
                        if t["progress"] == 100:
                            label = "✅ " + t["name"][:15]
                        if t["subject"]:
                            label = f"[{t['subject']}] {label}"

                        if st.button(
                            label,
                            key=f"cal_task_{t['id']}_{week_idx}_{col_idx}",
                            use_container_width=True,
                        ):
                            navigate("task_detail", task_id=t["id"])

                    if st.session_state.show_school:
                        for ne in neis_month_events.get(ds, []):
                            event_name = ne.get("EVENT_NM", "학사일정")
                            st.markdown(
                                f"<div class='school-pill'>🏫 {html.escape(event_name[:18])}</div>",
                                unsafe_allow_html=True
                            )

                        for e in events.get(ds, []):
                            st.markdown(
                                f"<div class='school-pill'>🏫 {html.escape(e['title'][:18])}</div>",
                                unsafe_allow_html=True
                            )

    st.divider()
    st.subheader("📌 예정된 테스크")

    upcoming = [
        t for t in tasks
        if date.fromisoformat(t["deadline"]) >= date.today()
    ]

    if not upcoming:
        st.info("등록된 예정 테스크가 없습니다. 오른쪽 위의 ＋ 테스크로 추가하세요.")

    for t in upcoming[:15]:
        c1, c2, c3 = st.columns([4, 2, 1])
        with c1:
            st.write(f"**{t['name']}**")
            st.caption(f"{t['subject'] or '기타'} · {t['task_type']} · 진행률 {t['progress']}%")
        with c2:
            st.write(f"마감 {t['deadline']}")
        with c3:
            if st.button("확인", key=f"up_{t['id']}"):
                navigate("task_detail", task_id=t["id"])
        st.progress(t["progress"] / 100)


# -----------------------------
# Add & Detail Task
# -----------------------------
def page_add_task():
    top_nav()
    st.title("＋ 테스크 설정")
    st.caption("마감 날짜를 캘린더에서 선택하면 그 날짜의 테스크 칸에 표시됩니다.")

    with st.form("add_task"):
        name = st.text_input("테스크 이름 *", placeholder="예: 화학 수행평가 보고서")
        task_type = st.selectbox(
            "테스크 종류",
            ["수행평가", "과제", "시험 준비", "발표", "일반 과제"]
        )
        subject = st.text_input(
            "과목",
            placeholder="예: 화학, 미적분, 생명과학, 화학 탐구"
        )

        st.markdown("**📅 테스크 날짜**")
        deadline = st.date_input(
            "캘린더에서 날짜 선택",
            value=date.today(),
            key="task_deadline",
        )

        guide = st.text_area(
            "테스크 내용",
            placeholder="해야 하는 내용, 평가 기준, 제출 형식 등 테스크와 관련된 내용을 적어주세요.",
            height=160,
        )
        notes = st.text_area(
            "특이사항",
            placeholder="알람에도 함께 표시할 내용을 적어주세요.",
            height=100,
        )
        materials = st.text_area(
            "준비물",
            placeholder="예: 출력물, 실험복, 발표 자료 등"
        )

        st.subheader("📎 안내 자료")
        st.caption("테스크 내용과 함께 확인할 파일, 사진, 링크를 등록할 수 있습니다.")
        uploaded = st.file_uploader(
            "파일 / 사진 첨부",
            accept_multiple_files=True,
            type=None,
            key="task_guide_files",
        )
        link_text = st.text_area(
            "링크",
            placeholder="https://example.com\n링크가 여러 개라면 한 줄에 하나씩 입력하세요.",
            key="task_guide_links",
        )

        st.subheader("🔔 알람 설정")
        alarm_enabled = st.checkbox("알람 사용", value=True)
        alarm_days = st.selectbox(
            "언제 알람할까요?",
            [0, 1, 2, 3, 5, 7],
            index=2,
            format_func=lambda x: "당일" if x == 0 else f"{x}일 전"
        )
        alarm_time = st.time_input(
            "알람 시간",
            value=datetime.strptime("18:00", "%H:%M").time()
        )

        submitted = st.form_submit_button(
            "테스크 저장",
            type="primary",
            use_container_width=True
        )

    if submitted:
        if not name.strip():
            st.error("테스크 이름을 입력해주세요.")
            return

        conn = db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tasks (
                name, task_type, subject, start_date, deadline, guide, notes,
                special_alarm_note, duration_type, progress,
                alarm_enabled, alarm_days_before, alarm_time,
                submission_checked, materials, materials_checked, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '일반', 0, ?, ?, ?, 0, ?, 0, ?)
        """, (
            name.strip(), task_type, subject, deadline.isoformat(), deadline.isoformat(),
            guide, notes, notes,
            int(alarm_enabled), alarm_days, alarm_time.strftime("%H:%M"),
            materials, datetime.now().isoformat()
        ))
        task_id = cur.lastrowid

        for safe_name, path in save_uploaded_files(uploaded, f"task_{task_id}"):
            cur.execute(
                "INSERT INTO task_files(task_id, original_name, saved_path) VALUES (?, ?, ?)",
                (task_id, safe_name, path)
            )

        for raw_url in link_text.splitlines():
            url = normalize_url(raw_url)
            if url:
                cur.execute(
                    "INSERT INTO task_links(task_id, url) VALUES (?, ?)",
                    (task_id, url)
                )

        conn.commit()
        conn.close()
        st.success("테스크가 저장되었습니다.")
        navigate("task_detail", task_id=task_id)


def page_task_detail():
    top_nav()
    task = get_task(st.session_state.task_id)

    if task is None:
        st.error("테스크를 찾을 수 없습니다.")
        if st.button("캘린더로 돌아가기"):
            navigate("calendar")
        return

    if st.button("← 캘린더"):
        navigate("calendar")

    st.title(f"📌 {task['name']}")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("마감일", task["deadline"])
    with c2:
        st.metric("진행률", f"{task['progress']}%")
    with c3:
        st.metric("과목", task["subject"] or "기타")
    with c4:
        st.metric("종류", task["task_type"])

    st.progress(task["progress"] / 100)

    st.subheader("📋 테스크 정보")
    st.write(f"**과목:** {task['subject'] or '기타'}")
    st.write(f"**종류:** {task['task_type']}")
    st.write(f"**날짜:** {task['deadline']}")

    if task["guide"]:
        st.subheader("📝 테스크 내용")
        st.info(task["guide"])

    if task["notes"]:
        st.subheader("📎 특이사항")
        st.write(task["notes"])

    if task["materials"]:
        st.subheader("🎒 준비물")
        st.write(task["materials"])

    st.subheader("📈 진행률 설정")
    progress = st.slider(
        "진행률",
        0, 100, int(task["progress"]), 5,
        key=f"progress_slider_{task['id']}"
    )
    if st.button("진행률 저장", type="primary"):
        conn = db()
        conn.execute("UPDATE tasks SET progress=? WHERE id=?", (progress, task["id"]))
        conn.commit()
        conn.close()
        st.success("진행률이 저장되었습니다.")
        st.rerun()

    st.subheader("✅ 제출 / 준비물 확인")
    c1, c2 = st.columns(2)
    with c1:
        submitted = st.checkbox(
            "제출 확인",
            value=bool(task["submission_checked"]),
            key=f"submit_check_{task['id']}"
        )
    with c2:
        material_check = st.checkbox(
            "준비물 챙김 확인",
            value=bool(task["materials_checked"]),
            key=f"material_check_{task['id']}"
        )
    if st.button("확인 상태 저장"):
        conn = db()
        conn.execute(
            "UPDATE tasks SET submission_checked=?, materials_checked=? WHERE id=?",
            (int(submitted), int(material_check), task["id"])
        )
        conn.commit()
        conn.close()
        st.success("확인 상태가 저장되었습니다.")
        st.rerun()

    st.subheader("🔔 알람")
    if task["alarm_enabled"]:
        when = "당일" if task["alarm_days_before"] == 0 else f"{task['alarm_days_before']}일 전"
        st.write(f"알람 **ON** · {when} · {task['alarm_time']}")
        if task["notes"]:
            st.warning(task["notes"])
    else:
        st.write("알람 OFF")

    st.subheader("📎 첨부 파일 / 사진")
    detail_upload = st.file_uploader(
        "이 테스크에 사진 또는 파일 추가",
        accept_multiple_files=True,
        type=None,
        key=f"detail_upload_{task['id']}"
    )

    if st.button("📎 파일 저장", key=f"save_detail_files_{task['id']}"):
        if detail_upload:
            conn = db()
            for safe_name, path in save_uploaded_files(
                detail_upload, f"task_{task['id']}"
            ):
                conn.execute(
                    "INSERT INTO task_files(task_id, original_name, saved_path) VALUES (?, ?, ?)",
                    (task["id"], safe_name, path)
                )
            conn.commit()
            conn.close()
            st.success("파일이 추가되었습니다.")
            st.rerun()
        else:
            st.info("추가할 파일을 먼저 선택해주세요.")

    files = get_task_files(task["id"])
    if files:
        for f in files:
            fp_path = Path(f["saved_path"])
            if fp_path.exists():
                if fp_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
                    st.image(
                        str(fp_path),
                        caption=f["original_name"],
                        use_container_width=False
                    )
                with open(fp_path, "rb") as fp:
                    st.download_button(
                        f"⬇️ {f['original_name']}",
                        fp.read(),
                        file_name=f["original_name"],
                        key=f"task_download_{f['id']}"
                    )
    else:
        st.caption("첨부된 파일이 없습니다.")

    st.subheader("🔗 등록된 링크")
    links = get_task_links(task["id"])
    if links:
        for i, link in enumerate(links, 1):
            st.link_button(
                f"🔗 링크 {i} 열기",
                link["url"],
                use_container_width=True
            )
            st.caption(link["url"])
    else:
        st.caption("이 테스크에 등록된 링크가 없습니다.")

    new_task_link = st.text_input(
        "이 테스크에 링크 추가",
        placeholder="https://...",
        key=f"detail_link_{task['id']}"
    )
    if st.button("🔗 링크 저장", key=f"save_detail_link_{task['id']}"):
        url = normalize_url(new_task_link)
        if url:
            conn = db()
            conn.execute(
                "INSERT INTO task_links(task_id, url) VALUES (?, ?)",
                (task["id"], url)
            )
            conn.commit()
            conn.close()
            st.success("링크가 추가되었습니다.")
            st.rerun()
        else:
            st.info("추가할 링크를 입력해주세요.")

    st.divider()
    if st.button("✏️ 테스크 수정", use_container_width=True):
        navigate("edit_task", task_id=task["id"])


# -----------------------------
# Edit task & School Schedule
# -----------------------------
def page_edit_task():
    top_nav()
    task = get_task(st.session_state.task_id)

    if task is None:
        navigate("calendar")
        return

    st.title("✏️ 테스크 수정")

    with st.form("edit_task"):
        name = st.text_input("테스크 이름 *", value=task["name"])
        types = ["수행평가", "과제", "시험 준비", "발표", "일반 과제"]
        current_type = task["task_type"] if task["task_type"] in types else "일반 과제"
        task_type = st.selectbox("테스크 종류", types, index=types.index(current_type))
        subject = st.text_input(
            "과목",
            value=task["subject"] or "",
            placeholder="예: 화학, 미적분, 생명과학, 화학 탐구"
        )

        st.markdown("**📅 테스크 날짜**")
        deadline = st.date_input(
            "캘린더에서 날짜 선택",
            date.fromisoformat(task["deadline"]),
            key=f"edit_deadline_{task['id']}",
        )

        guide = st.text_area("테스크 내용", value=task["guide"], height=160)
        notes = st.text_area("특이사항", value=task["notes"], height=100,
                             help="이 내용은 알람에도 함께 표시됩니다.")
        materials = st.text_area("준비물", value=task["materials"])

        st.subheader("📎 안내 자료 추가")
        new_files = st.file_uploader(
            "파일 / 사진 추가",
            accept_multiple_files=True,
            type=None,
            key=f"edit_files_{task['id']}",
        )
        new_links = st.text_area(
            "링크 추가",
            placeholder="https://example.com\n여러 개라면 한 줄에 하나씩 입력하세요.",
            key=f"edit_links_{task['id']}",
        )

        st.subheader("🔔 알람 설정")
        alarm_enabled = st.checkbox("알람 사용", value=bool(task["alarm_enabled"]))
        days_options = [0, 1, 2, 3, 5, 7]
        current_days = int(task["alarm_days_before"])
        if current_days not in days_options:
            current_days = 1
        alarm_days = st.selectbox(
            "알람 시점",
            days_options,
            index=days_options.index(current_days),
            format_func=lambda x: "당일" if x == 0 else f"{x}일 전"
        )
        alarm_time = st.time_input(
            "알람 시간",
            value=datetime.strptime(task["alarm_time"], "%H:%M").time()
        )

        save = st.form_submit_button(
            "수정 내용 저장",
            type="primary",
            use_container_width=True
        )

    if save:
        if not name.strip():
            st.error("테스크 이름을 입력해주세요.")
            return

        conn = db()
        conn.execute("""
            UPDATE tasks SET
                name=?, task_type=?, subject=?, start_date=?, deadline=?,
                guide=?, notes=?, special_alarm_note=?, duration_type=?,
                alarm_enabled=?, alarm_days_before=?, alarm_time=?, materials=?
            WHERE id=?
        """, (
            name.strip(), task_type, subject, deadline.isoformat(), deadline.isoformat(),
            guide, notes, notes,
            "일반", int(alarm_enabled), alarm_days, alarm_time.strftime("%H:%M"),
            materials, task["id"]
        ))

        for safe_name, path in save_uploaded_files(new_files, f"task_{task['id']}"):
            conn.execute(
                "INSERT INTO task_files(task_id, original_name, saved_path) VALUES (?, ?, ?)",
                (task["id"], safe_name, path)
            )

        for raw_url in new_links.splitlines():
            url = normalize_url(raw_url)
            if url:
                conn.execute(
                    "INSERT INTO task_links(task_id, url) VALUES (?, ?)",
                    (task["id"], url)
                )

        conn.commit()
        conn.close()
        st.success("수정되었습니다.")
        navigate("task_detail", task_id=task["id"])


def page_add_school():
    top_nav()
    st.title("＋ 학교 학사일정 추가")
    st.caption("학사일정은 직접 등록하면 캘린더에서 선택적으로 표시할 수 있습니다.")

    with st.form("school"):
        title = st.text_input("일정 이름 *", placeholder="예: 중간고사")
        event_date = st.date_input("날짜", date.today())
        notes = st.text_area("설명")
        save = st.form_submit_button("저장", type="primary", use_container_width=True)

    if save:
        if not title.strip():
            st.error("일정 이름을 입력해주세요.")
            return
        conn = db()
        conn.execute(
            "INSERT INTO school_events(title,event_date,notes,created_at) VALUES(?,?,?,?)",
            (title.strip(), event_date.isoformat(), notes, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        st.success("학사일정이 저장되었습니다.")
        navigate("calendar")


def page_neis_schedule():
    top_nav()
    st.title("🏫 실제 학교 학사일정")
    st.caption("나이스 교육정보 개방 포털의 학교별 학사일정을 불러옵니다.")

    key = neis_api_key()
    if not key:
        st.warning(
            "먼저 Streamlit Secrets에 NEIS_API_KEY를 등록해야 합니다. "
            "나이스 교육정보 개방 포털에서 Open API 인증키를 발급받을 수 있습니다."
        )
        st.markdown(
            "인증키 발급 안내: "
            "https://open.neis.go.kr/portal/guide/apiGuidePage.do"
        )

    offices = {
        "서울": "B10", "부산": "C10", "대구": "D10", "인천": "E10",
        "광주": "F10", "대전": "G10", "울산": "H10", "세종": "I10",
        "경기": "J10", "강원": "K10", "충북": "M10", "충남": "N10",
        "전북": "P10", "전남": "Q10", "경북": "R10", "경남": "S10",
        "제주": "T10",
    }

    c1, c2 = st.columns(2)
    with c1:
        region_name = st.selectbox("교육청", list(offices.keys()))
    with c2:
        school_name = st.text_input(
            "학교명",
            placeholder="예: ○○고등학교",
        )

    if st.button("🔎 학교 검색", type="primary", use_container_width=True):
        if not school_name.strip():
            st.error("학교명을 입력해주세요.")
        elif not key:
            st.error("NEIS_API_KEY를 먼저 설정해주세요.")
        else:
            rows, err = neis_school_search(
                school_name, offices[region_name]
            )
            if err:
                st.error(err)
            elif not rows:
                st.warning("학교를 찾지 못했습니다. 학교명을 다시 확인해주세요.")
            else:
                st.session_state["neis_school_results"] = rows
                st.session_state["neis_office_code"] = offices[region_name]

    results = st.session_state.get("neis_school_results", [])

    if results:
        options = {
            f"{r.get('SCHUL_NM', '')} | {r.get('ORG_RDNMA', '')}": r
            for r in results
        }
        selected_label = st.selectbox(
            "학교 선택",
            list(options.keys())
        )
        selected = options[selected_label]

        st.session_state["neis_school_code"] = selected.get("SD_SCHUL_CODE")
        st.session_state["neis_school_name"] = selected.get("SCHUL_NM")

        st.success(
            f"선택한 학교: {selected.get('SCHUL_NM')} "
            f"({selected.get('SD_SCHUL_CODE')})"
        )

        if st.button("💾 이 학교를 학사일정 학교로 저장"):
            # 세션이 사라져도 저장되도록 DB에 지속 보존
            save_school_config(
                selected.get("SCHUL_NM"),
                selected.get("SD_SCHUL_CODE"),
                st.session_state["neis_office_code"]
            )
            st.success("학교 설정이 영구 저장되었습니다.")

    saved = get_saved_school_config()

    if saved:
        st.divider()
        st.subheader(f"📅 현재 저장된 학교: {saved['name']}")

        y, m = st.session_state.year, st.session_state.month
        first_day = date(y, m, 1)
        last_day = date(y, m, calendar.monthrange(y, m)[1])

        rows, err = neis_calendar(
            saved["code"],
            saved["office"],
            first_day,
            last_day,
        )

        if err:
            st.error(err)
        elif not rows:
            st.info("해당 월의 학사일정이 없습니다.")
        else:
            for row in rows:
                dt = row.get("AA_YMD", "")
                event = row.get("EVENT_NM", "")
                content = row.get("EVENT_CNTNT", "")
                st.write(
                    f"🏫 **{dt} — {event}**"
                    + (f" · {content}" if content else "")
                )


# -----------------------------
# Archive Logic
# -----------------------------
def page_archive():
    top_nav()
    st.title("📂 이전 과제 / 구상 내용")

    c1, c2 = st.columns([3, 1])
    with c1:
        category = st.radio(
            "분류",
            ["전체", "이전 과제", "구상 내용"],
            horizontal=True,
            index=0,
        )
    with c2:
        if st.button("＋ 등록", type="primary", use_container_width=True):
            navigate("add_archive")

    search = st.text_input(
        "🔍 검색",
        placeholder="제목이나 내용으로 검색하세요."
    )

    items = get_archives(category, search)

    st.divider()

    if not items:
        st.info("등록된 자료가 없습니다.")

    for item in items:
        icon = "📚" if item["category"] == "이전 과제" else "💡"
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f"### {icon} {item['title']}")
            st.caption(item["category"])
            preview = item["content"] or ""
            st.write(preview[:180] + ("..." if len(preview) > 180 else ""))
        with c2:
            if st.button("자세히", key=f"archive_open_{item['id']}"):
                navigate("archive_detail", archive_id=item["id"])
        st.divider()


def page_archive_detail():
    top_nav()
    item = get_archive(st.session_state.archive_id)

    # 파라미터 미선택/None 발생 시 즉각 리턴 처리로 안전성 확보
    if item is None:
        st.error("아카이브 항목을 찾을 수 없습니다.")
        if st.button("목록으로 돌아가기"):
            navigate("archive")
        return

    if st.button("← 이전 목록"):
        navigate("archive")

    icon = "📚" if item["category"] == "이전 과제" else "💡"
    st.title(f"{icon} {item['title']}")
    st.caption(item["category"])

    st.divider()
    st.subheader("내용")
    st.write(item["content"] or "내용이 없습니다.")

    if item["link"]:
        st.subheader("🔗 링크")
        st.markdown(f"[🔗 링크 열기]({item['link']})")

    files = get_archive_files(item["id"])
    if files:
        st.subheader("📎 첨부 파일")
        for f in files:
            p = Path(f["saved_path"])
            if p.exists():
                if p.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
                    st.image(str(p), caption=f["original_name"], use_container_width=False)
                with open(p, "rb") as fp:
                    st.download_button(
                        f"⬇️ {f['original_name']}",
                        fp.read(),
                        file_name=f["original_name"],
                        key=f"archive_download_{f['id']}"
                    )


def page_add_archive():
    top_nav()
    st.title("＋ 이전 과제 / 구상 내용 등록")

    default_category = st.session_state.pop(
        "prefill_archive_category", "이전 과제"
    )
    default_index = 0 if default_category == "이전 과제" else 1

    with st.form("archive_add"):
        category = st.radio(
            "무엇을 등록할까요?",
            ["이전 과제", "구상 내용"],
            index=default_index,
            horizontal=True,
        )
        title = st.text_input("제목 *")
        content = st.text_area("내용", height=300)
        link = st.text_input("링크", placeholder="https://...")
        files = st.file_uploader(
            "파일 / 사진 첨부",
            accept_multiple_files=True,
            type=None,
        )
        save = st.form_submit_button(
            "등록하기",
            type="primary",
            use_container_width=True
        )

    if save:
        if not title.strip():
            st.error("제목을 입력해주세요.")
            return

        link = normalize_url(link)

        conn = db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO archives(category,title,content,link,created_at) VALUES(?,?,?,?,?)",
            (category, title.strip(), content, link, datetime.now().isoformat())
        )
        archive_id = cur.lastrowid

        for safe_name, path in save_uploaded_files(files, f"archive_{archive_id}"):
            cur.execute(
                "INSERT INTO archive_files(archive_id,original_name,saved_path) VALUES(?,?,?)",
                (archive_id, safe_name, path)
            )

        conn.commit()
        conn.close()

        st.success("등록되었습니다.")
        navigate("archive_detail", archive_id=archive_id)


# -----------------------------
# Router
# -----------------------------
page = st.session_state.page

if page == "home":
    page_home()
elif page == "calendar":
    page_calendar()
elif page == "add_task":
    page_add_task()
elif page == "task_detail":
    page_task_detail()
elif page == "edit_task":
    page_edit_task()
elif page == "add_school":
    page_add_school()
elif page == "neis_schedule":
    page_neis_schedule()
elif page == "archive":
    page_archive()
elif page == "archive_detail":
    page_archive_detail()
elif page == "add_archive":
    page_add_archive()
else:
    navigate("home")
