import streamlit as st
import sqlite3
import os
import json
from datetime import datetime, date, timedelta
from pathlib import Path
import calendar
import uuid


# =========================================================
# 기본 설정
# =========================================================

st.set_page_config(
    page_title="해야지",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

DB_FILE = "todo_app.db"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# =========================================================
# 데이터베이스
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            deadline TEXT NOT NULL,
            start_date TEXT,
            task_type TEXT DEFAULT '일반 과제',
            notes TEXT,
            instructions TEXT,
            progress INTEGER DEFAULT 0,
            alarm_enabled INTEGER DEFAULT 0,
            alarm_days_before INTEGER DEFAULT 0,
            alarm_time TEXT DEFAULT '18:00',
            long_task INTEGER DEFAULT 0,
            special_note TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            file_name TEXT,
            file_path TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            url TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS school_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            schedule_date TEXT NOT NULL,
            description TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT,
            link TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS archive_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archive_id INTEGER,
            file_name TEXT,
            file_path TEXT,
            FOREIGN KEY(archive_id) REFERENCES archive(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# 세션 상태
# =========================================================

if "page" not in st.session_state:
    st.session_state.page = "home"

if "selected_task" not in st.session_state:
    st.session_state.selected_task = None

if "selected_archive" not in st.session_state:
    st.session_state.selected_archive = None

if "calendar_year" not in st.session_state:
    st.session_state.calendar_year = date.today().year

if "calendar_month" not in st.session_state:
    st.session_state.calendar_month = date.today().month


# =========================================================
# 공통 함수
# =========================================================

def go(page):
    st.session_state.page = page
    st.rerun()


def get_tasks():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM tasks ORDER BY deadline ASC"
    ).fetchall()
    conn.close()
    return rows


def get_task(task_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM tasks WHERE id = ?",
        (task_id,)
    ).fetchone()
    conn.close()
    return row


def get_archive_items(category=None):
    conn = get_db()

    if category is None or category == "전체":
        rows = conn.execute(
            "SELECT * FROM archive ORDER BY created_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM archive WHERE category = ? ORDER BY created_at DESC",
            (category,)
        ).fetchall()

    conn.close()
    return rows


def get_archive(archive_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM archive WHERE id = ?",
        (archive_id,)
    ).fetchone()
    conn.close()
    return row


def get_task_links(task_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM task_links WHERE task_id = ?",
        (task_id,)
    ).fetchall()
    conn.close()
    return rows


def get_task_files(task_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM task_files WHERE task_id = ?",
        (task_id,)
    ).fetchall()
    conn.close()
    return rows


def get_archive_files(archive_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM archive_files WHERE archive_id = ?",
        (archive_id,)
    ).fetchall()
    conn.close()
    return rows


# =========================================================
# CSS
# =========================================================

st.markdown("""
<style>

.main {
    background-color: #fafafa;
}

.block-container {
    padding-top: 2rem;
    max-width: 1200px;
}

.big-title {
    font-size: 42px;
    font-weight: 800;
    text-align: center;
    margin-top: 100px;
}

.subtitle {
    text-align: center;
    color: #777;
    font-size: 17px;
    margin-bottom: 35px;
}

.task-card {
    border: 1px solid #e5e5e5;
    border-radius: 14px;
    padding: 15px;
    margin-bottom: 10px;
    background-color: white;
}

.calendar-day {
    min-height: 120px;
    border: 1px solid #eeeeee;
    border-radius: 10px;
    padding: 8px;
    background: white;
}

.calendar-date {
    font-weight: bold;
    margin-bottom: 5px;
}

.calendar-task {
    background: #eef4ff;
    border-radius: 6px;
    padding: 5px;
    margin-top: 4px;
    font-size: 12px;
}

.calendar-school {
    background: #fff2cc;
    border-radius: 6px;
    padding: 5px;
    margin-top: 4px;
    font-size: 12px;
}

.progress-text {
    font-size: 13px;
    color: #666;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# 시작 화면
# =========================================================

def home_page():

    st.markdown(
        '<div class="big-title">📚 해야지</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">해야 할 일을 잊지 않도록, 한눈에 관리하는 학습 일정 관리 앱</div>',
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        if st.button(
            "🚀 시작하기",
            use_container_width=True,
            type="primary"
        ):
            go("calendar")


# =========================================================
# 상단 네비게이션
# =========================================================

def navigation():

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if st.button("📚 해야지", key="logo"):
            go("calendar")

    with col2:
        if st.button("📂 이전 과제 / 구상", use_container_width=True):
            go("archive")

    with col3:
        if st.button("＋ 과제 추가", use_container_width=True):
            go("add_task")

    st.divider()


# =========================================================
# 알람 확인
# =========================================================

def alarm_check():

    today = date.today()
    now = datetime.now().strftime("%H:%M")

    alarms = []

    for task in get_tasks():

        if not task["alarm_enabled"]:
            continue

        deadline = date.fromisoformat(task["deadline"])
        alarm_date = deadline - timedelta(days=task["alarm_days_before"])

        if alarm_date == today:
            alarms.append(task)

    if alarms:
        st.warning("🔔 오늘 확인해야 할 알림이 있어요!")

        for task in alarms:
            if task["progress"] >= 100:
                continue

            st.info(
                f"**{task['name']}**\n\n"
                f"마감일: {task['deadline']}\n\n"
                f"진행률: {task['progress']}%\n\n"
                f"특이사항: {task['special_note'] or '없음'}"
            )


# =========================================================
# 캘린더
# =========================================================

def calendar_page():

    navigation()

    st.title("📅 일정 캘린더")

    alarm_check()

    # 월 이동
    col1, col2, col3 = st.columns([1, 3, 1])

    with col1:
        if st.button("◀ 이전 달"):
            if st.session_state.calendar_month == 1:
                st.session_state.calendar_year -= 1
                st.session_state.calendar_month = 12
            else:
                st.session_state.calendar_month -= 1
            st.rerun()

    with col2:
        st.markdown(
            f"<h2 style='text-align:center;'>"
            f"{st.session_state.calendar_year}년 "
            f"{st.session_state.calendar_month}월"
            f"</h2>",
            unsafe_allow_html=True
        )

    with col3:
        if st.button("다음 달 ▶"):
            if st.session_state.calendar_month == 12:
                st.session_state.calendar_year += 1
                st.session_state.calendar_month = 1
            else:
                st.session_state.calendar_month += 1
            st.rerun()

    show_school = st.checkbox(
        "🏫 학교 학사일정 표시",
        value=True
    )

    year = st.session_state.calendar_year
    month = st.session_state.calendar_month

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    tasks = get_tasks()

    conn = get_db()
    school_events = conn.execute(
        """
        SELECT * FROM school_schedule
        WHERE substr(schedule_date,1,7) = ?
        """,
        (f"{year:04d}-{month:02d}",)
    ).fetchall()
    conn.close()

    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]

    cols = st.columns(7)

    for i, name in enumerate(weekday_names):
        cols[i].markdown(
            f"<b style='text-align:center;display:block'>{name}</b>",
            unsafe_allow_html=True
        )

    for week in weeks:

        cols = st.columns(7)

        for i, day in enumerate(week):

            with cols[i]:

                if day == 0:
                    st.write("")
                    continue

                current_date = date(year, month, day)
                date_str = current_date.isoformat()

                st.markdown(
                    f"<div class='calendar-day'>"
                    f"<div class='calendar-date'>{day}</div>",
                    unsafe_allow_html=True
                )

                # 과제 표시
                for task in tasks:

                    if task["deadline"] == date_str:

                        if st.button(
                            f"📌 {task['name'][:15]}",
                            key=f"task_{task['id']}_{date_str}",
                            use_container_width=True
                        ):
                            st.session_state.selected_task = task["id"]
                            go("task_detail")

                # 시작일 표시
                for task in tasks:

                    if task["start_date"] == date_str:

                        if task["deadline"] != date_str:
                            st.caption(
                                f"▶ {task['name'][:15]} 시작"
                            )

                # 학교 일정
                if show_school:

                    for event in school_events:

                        if event["schedule_date"] == date_str:
                            st.markdown(
                                f"<div class='calendar-school'>"
                                f"🏫 {event['title']}"
                                f"</div>",
                                unsafe_allow_html=True
                            )

                st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.subheader("📌 예정된 과제")

    upcoming = []

    for task in tasks:

        deadline = date.fromisoformat(task["deadline"])

        if deadline >= date.today():
            upcoming.append(task)

    if not upcoming:
        st.info("예정된 과제가 없습니다.")

    for task in upcoming[:10]:

        col1, col2, col3 = st.columns([4, 2, 1])

        with col1:
            st.write(f"**{task['name']}**")

        with col2:
            st.write(f"마감: {task['deadline']}")

        with col3:
            if st.button(
                "확인",
                key=f"upcoming_{task['id']}"
            ):
                st.session_state.selected_task = task["id"]
                go("task_detail")

        st.progress(task["progress"] / 100)

        st.caption(
            f"진행률 {task['progress']}% · "
            f"{'⏰ 장기 활동' if task['long_task'] else '⚡ 일반 활동'}"
        )


# =========================================================
# 과제 추가
# =========================================================

def add_task_page():

    navigation()

    st.title("＋ 해야 할 일 추가")

    with st.form("add_task_form"):

        name = st.text_input(
            "해야 할 일 이름 *",
            placeholder="예: 화학 수행평가 보고서"
        )

        task_type = st.selectbox(
            "종류",
            [
                "수행평가",
                "시험 준비",
                "과제",
                "발표",
                "일반 과제"
            ]
        )

        col1, col2 = st.columns(2)

        with col1:
            start_date = st.date_input(
                "시작일",
                value=date.today()
            )

        with col2:
            deadline = st.date_input(
                "마감일",
                value=date.today()
            )

        notes = st.text_area(
            "특이사항",
            placeholder="예: 발표 자료 10장 이내"
        )

        instructions = st.text_area(
            "수행평가 안내 / 해야 할 내용",
            placeholder="예: 교과서 3단원 내용을 활용하여 보고서 작성"
        )

        special_note = st.text_area(
            "알람에 함께 표시할 특이사항",
            placeholder="예: 출력물 꼭 챙기기"
        )

        long_task = st.checkbox(
            "⏳ 시간이 오래 필요한 활동인가요?"
        )

        st.subheader("🔔 알람 설정")

        alarm_enabled = st.checkbox(
            "알람 사용",
            value=True
        )

        alarm_days_before = st.selectbox(
            "언제 알람을 받을까요?",
            [
                0,
                1,
                2,
                3,
                7
            ],
            format_func=lambda x:
                "당일" if x == 0
                else f"{x}일 전"
        )

        alarm_time = st.time_input(
            "알람 시간",
            value=datetime.strptime(
                "18:00",
                "%H:%M"
            ).time()
        )

        submitted = st.form_submit_button(
            "저장하기",
            type="primary",
            use_container_width=True
        )

        if submitted:

            if not name.strip():
                st.error("해야 할 일 이름을 입력해주세요.")
                return

            if deadline < start_date:
                st.error("마감일은 시작일보다 빠를 수 없습니다.")
                return

            conn = get_db()

            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO tasks
                (
                    name,
                    deadline,
                    start_date,
                    task_type,
                    notes,
                    instructions,
                    progress,
                    alarm_enabled,
                    alarm_days_before,
                    alarm_time,
                    long_task,
                    special_note,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    deadline.isoformat(),
                    start_date.isoformat(),
                    task_type,
                    notes,
                    instructions,
                    0,
                    int(alarm_enabled),
                    alarm_days_before,
                    alarm_time.strftime("%H:%M"),
                    int(long_task),
                    special_note,
                    datetime.now().isoformat()
                )
            )

            conn.commit()
            conn.close()

            st.success("과제가 저장되었습니다!")

            st.session_state.selected_task = cur.lastrowid

            st.session_state.page = "task_detail"

            st.rerun()


# =========================================================
# 과제 상세
# =========================================================

def task_detail_page():

    navigation()

    task_id = st.session_state.selected_task

    if task_id is None:
        go("calendar")

    task = get_task(task_id)

    if task is None:
        st.error("과제를 찾을 수 없습니다.")
        return

    if st.button("← 캘린더로 돌아가기"):
        go("calendar")

    st.title(f"📌 {task['name']}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "마감일",
            task["deadline"]
        )

    with col2:
        st.metric(
            "진행률",
            f"{task['progress']}%"
        )

    with col3:
        if task["long_task"]:
            st.metric("활동 유형", "⏳ 장기 활동")
        else:
            st.metric("활동 유형", "⚡ 일반 활동")

    st.progress(task["progress"] / 100)

    st.divider()

    st.subheader("📋 과제 정보")

    st.write(
        f"**종류:** {task['task_type']}"
    )

    st.write(
        f"**시작일:** {task['start_date']}"
    )

    st.write(
        f"**마감일:** {task['deadline']}"
    )

    if task["instructions"]:
        st.subheader("📝 수행평가 안내 / 내용")
        st.info(task["instructions"])

    if task["notes"]:
        st.subheader("📎 특이사항")
        st.write(task["notes"])

    if task["special_note"]:
        st.subheader("🔔 알람에 표시할 내용")
        st.warning(task["special_note"])

    st.subheader("📈 진행률")

    progress = st.slider(
        "진행률",
        0,
        100,
        int(task["progress"]),
        step=10,
        key=f"progress_{task_id}"
    )

    if st.button("진행률 저장", type="primary"):
        conn = get_db()

        conn.execute(
            "UPDATE tasks SET progress = ? WHERE id = ?",
            (progress, task_id)
        )

        conn.commit()
        conn.close()

        st.success("진행률이 저장되었습니다.")
        st.rerun()

    st.divider()

    st.subheader("🔔 알람")

    if task["alarm_enabled"]:

        alarm_text = (
            "당일"
            if task["alarm_days_before"] == 0
            else f"{task['alarm_days_before']}일 전"
        )

        st.write(
            f"알람: **켜짐** · "
            f"{alarm_text} · "
            f"{task['alarm_time']}"
        )

    else:
        st.write("알람: 꺼짐")

    st.divider()

    st.subheader("📎 첨부 파일")

    files = get_task_files(task_id)

    if files:

        for file in files:

            path = file["file_path"]

            if os.path.exists(path):

                with open(path, "rb") as f:

                    st.download_button(
                        label=f"📄 {file['file_name']}",
                        data=f.read(),
                        file_name=file["file_name"],
                        key=f"download_task_{file['id']}"
                    )

    else:
        st.caption("첨부된 파일이 없습니다.")

    st.subheader("🔗 링크")

    links = get_task_links(task_id)

    if links:

        for link in links:

            st.markdown(
                f"[🔗 링크 열기]({link['url']})"
            )

    else:
        st.caption("등록된 링크가 없습니다.")

    st.divider()

    if st.button(
        "✏️ 과제 수정",
        use_container_width=True
    ):
        go("edit_task")


# =========================================================
# 과제 수정
# =========================================================

def edit_task_page():

    navigation()

    task_id = st.session_state.selected_task
    task = get_task(task_id)

    if task is None:
        go("calendar")

    st.title("✏️ 과제 수정")

    with st.form("edit_task_form"):

        name = st.text_input(
            "해야 할 일 이름",
            value=task["name"]
        )

        task_type = st.selectbox(
            "종류",
            [
                "수행평가",
                "시험 준비",
                "과제",
                "발표",
                "일반 과제"
            ],
            index=[
                "수행평가",
                "시험 준비",
                "과제",
                "발표",
                "일반 과제"
            ].index(task["task_type"])
        )

        start_date = st.date_input(
            "시작일",
            value=date.fromisoformat(task["start_date"])
        )

        deadline = st.date_input(
            "마감일",
            value=date.fromisoformat(task["deadline"])
        )

        notes = st.text_area(
            "특이사항",
            value=task["notes"] or ""
        )

        instructions = st.text_area(
            "수행평가 안내 / 해야 할 내용",
            value=task["instructions"] or ""
        )

        special_note = st.text_area(
            "알람 특이사항",
            value=task["special_note"] or ""
        )

        long_task = st.checkbox(
            "⏳ 시간이 오래 필요한 활동",
            value=bool(task["long_task"])
        )

        alarm_enabled = st.checkbox(
            "🔔 알람 사용",
            value=bool(task["alarm_enabled"])
        )

        alarm_days_before = st.selectbox(
            "알람 시점",
            [0, 1, 2, 3, 7],
            index=[0, 1, 2, 3, 7].index(
                task["alarm_days_before"]
            ),
            format_func=lambda x:
                "당일" if x == 0
                else f"{x}일 전"
        )

        alarm_time = st.time_input(
            "알람 시간",
            value=datetime.strptime(
                task["alarm_time"],
                "%H:%M"
            ).time()
        )

        submitted = st.form_submit_button(
            "수정 내용 저장",
            type="primary",
            use_container_width=True
        )

        if submitted:

            conn = get_db()

            conn.execute(
                """
                UPDATE tasks
                SET name = ?,
                    deadline = ?,
                    start_date = ?,
                    task_type = ?,
                    notes = ?,
                    instructions = ?,
                    alarm_enabled = ?,
                    alarm_days_before = ?,
                    alarm_time = ?,
                    long_task = ?,
                    special_note = ?
                WHERE id = ?
                """,
                (
                    name,
                    deadline.isoformat(),
                    start_date.isoformat(),
                    task_type,
                    notes,
                    instructions,
                    int(alarm_enabled),
                    alarm_days_before,
                    alarm_time.strftime("%H:%M"),
                    int(long_task),
                    special_note,
                    task_id
                )
            )

            conn.commit()
            conn.close()

            st.success("수정되었습니다.")

            go("task_detail")


# =========================================================
# 이전 과제 / 구상 내용
# =========================================================

def archive_page():

    navigation()

    st.title("📂 이전 과제 / 구상 내용")

    tab = st.radio(
        "보기",
        [
            "전체",
            "이전 과제",
            "구상 내용"
        ],
        horizontal=True
    )

    search = st.text_input(
        "🔍 검색",
        placeholder="제목이나 내용을 검색하세요"
    )

    if tab == "전체":
        category = None
    else:
        category = tab

    items = get_archive_items(category)

    if search:

        items = [
            item for item in items
            if search.lower() in
            (
                (item["title"] or "") +
                (item["content"] or "")
            ).lower()
        ]

    st.divider()

    if not items:

        st.info("등록된 내용이 없습니다.")

    for item in items:

        col1, col2 = st.columns([5, 1])

        with col1:

            st.markdown(
                f"### {item['title']}"
            )

            st.caption(
                f"{'📚 이전 과제' if item['category'] == '이전 과제' else '💡 구상 내용'}"
            )

            preview = item["content"] or ""

            if len(preview) > 100:
                preview = preview[:100] + "..."

            st.write(preview)

        with col2:

            if st.button(
                "자세히",
                key=f"archive_{item['id']}"
            ):

                st.session_state.selected_archive = item["id"]

                go("archive_detail")

        st.divider()

    if st.button(
        "＋ 새로운 내용 등록",
        type="primary",
        use_container_width=True
    ):
        go("add_archive")


# =========================================================
# 이전 과제 / 구상 상세
# =========================================================

def archive_detail_page():

    navigation()

    archive_id = st.session_state.selected_archive

    item = get_archive(archive_id)

    if item is None:
        go("archive")

    if st.button("← 목록으로 돌아가기"):
        go("archive")

    icon = (
        "📚"
        if item["category"] == "이전 과제"
        else "💡"
    )

    st.title(f"{icon} {item['title']}")

    st.caption(
        f"분류: {item['category']}"
    )

    st.divider()

    st.subheader("내용")

    st.write(
        item["content"] or "내용이 없습니다."
    )

    if item["link"]:

        st.subheader("🔗 링크")

        st.markdown(
            f"[링크 열기]({item['link']})"
        )

    files = get_archive_files(archive_id)

    if files:

        st.subheader("📎 첨부 파일")

        for file in files:

            path = file["file_path"]

            if os.path.exists(path):

                with open(path, "rb") as f:

                    st.download_button(
                        f"📄 {file['file_name']}",
                        f.read(),
                        file_name=file["file_name"],
                        key=f"archive_file_{file['id']}"
                    )


# =========================================================
# 이전 과제 / 구상 등록
# =========================================================

def add_archive_page():

    navigation()

    st.title("＋ 이전 과제 / 구상 내용 등록")

    with st.form("archive_form"):

        category = st.radio(
            "무엇을 등록할까요?",
            [
                "이전 과제",
                "구상 내용"
            ],
            horizontal=True
        )

        title = st.text_input(
            "제목 *",
            placeholder="예: pKa와 약물 흡수 탐구"
        )

        content = st.text_area(
            "내용",
            height=250,
            placeholder="과제 내용이나 구상한 아이디어를 기록하세요."
        )

        link = st.text_input(
            "링크",
            placeholder="https://..."
        )

        uploaded_files = st.file_uploader(
            "파일 첨부",
            accept_multiple_files=True
        )

        submitted = st.form_submit_button(
            "등록하기",
            type="primary",
            use_container_width=True
        )

        if submitted:

            if not title.strip():
                st.error("제목을 입력해주세요.")
                return

            conn = get_db()

            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO archive
                (title, category, content, link, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    title,
                    category,
                    content,
                    link,
                    datetime.now().isoformat()
                )
            )

            archive_id = cur.lastrowid

            # 파일 저장
            if uploaded_files:

                for uploaded_file in uploaded_files:

                    unique_name = (
                        str(uuid.uuid4()) +
                        "_" +
                        uploaded_file.name
                    )

                    file_path = (
                        UPLOAD_DIR /
                        unique_name
                    )

                    with open(
                        file_path,
                        "wb"
                    ) as f:
                        f.write(
                            uploaded_file.getbuffer()
                        )

                    cur.execute(
                        """
                        INSERT INTO archive_files
                        (archive_id, file_name, file_path)
                        VALUES (?, ?, ?)
                        """,
                        (
                            archive_id,
                            uploaded_file.name,
                            str(file_path)
                        )
                    )

            conn.commit()
            conn.close()

            st.success("등록되었습니다.")

            st.session_state.selected_archive = archive_id

            go("archive_detail")


# =========================================================
# 학교 학사일정 등록
# =========================================================

def school_schedule_page():

    navigation()

    st.title("🏫 학교 학사일정")

    st.info(
        "학교 학사일정은 필요한 경우 직접 등록할 수 있습니다."
    )

    with st.form("school_schedule_form"):

        title = st.text_input(
            "일정 이름",
            placeholder="예: 중간고사"
        )

        schedule_date = st.date_input(
            "날짜",
            value=date.today()
        )

        description = st.text_area(
            "설명"
        )

        submitted = st.form_submit_button(
            "학사일정 추가",
            type="primary"
        )

        if submitted:

            if not title.strip():
                st.error("일정 이름을 입력해주세요.")
                return

            conn = get_db()

            conn.execute(
                """
                INSERT INTO school_schedule
                (title, schedule_date, description)
                VALUES (?, ?, ?)
                """,
                (
                    title,
                    schedule_date.isoformat(),
                    description
                )
            )

            conn.commit()
            conn.close()

            st.success("학사일정이 추가되었습니다.")

    st.divider()

    conn = get_db()

    events = conn.execute(
        """
        SELECT * FROM school_schedule
        ORDER BY schedule_date
        """
    ).fetchall()

    conn.close()

    for event in events:

        st.write(
            f"🏫 **{event['schedule_date']}** "
            f"- {event['title']}"
        )

        if event["description"]:
            st.caption(
                event["description"]
            )


# =========================================================
# 페이지 라우팅
# =========================================================

page = st.session_state.page

if page == "home":
    home_page()

elif page == "calendar":
    calendar_page()

elif page == "add_task":
    add_task_page()

elif page == "task_detail":
    task_detail_page()

elif page == "edit_task":
    edit_task_page()

elif page == "archive":
    archive_page()

elif page == "archive_detail":
    archive_detail_page()

elif page == "add_archive":
    add_archive_page()

elif page == "school_schedule":
    school_schedule_page()
