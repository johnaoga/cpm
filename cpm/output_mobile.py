"""Generate a mobile-responsive HTML programme page.

The output is a self-contained HTML file inspired by the Benelux meeting
mobile programme.  It embeds all presentation data as a JSON array and
renders them dynamically with jQuery and W3.CSS.

Conference metadata (title, dates, etc.) is read from the LaTeX config
so that the same ``latex_config.json`` feeds both the LaTeX book and
the mobile page.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Program, Session, SlotKind, TimeSlot, build_topic_display_names


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(text, quote=True)


def _slot_start_datetime(day: int, ts: TimeSlot, base_dates: list[str]) -> str:
    """Build an ISO-ish datetime string for a slot start.

    If *base_dates* contains entries like ``"March 24, 2026"``, parse
    them and combine with the slot time.  Otherwise fall back to a
    synthetic date ``2025-01-{day}``.
    """
    time_str = ts.start.replace(".", ":")
    h, m = (int(x) for x in time_str.split(":"))

    if base_dates and day - 1 < len(base_dates):
        raw = base_dates[day - 1]
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                dt = dt.replace(hour=h, minute=m)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

    # Fallback: synthetic date
    return f"2025-01-{day:02d} {h:02d}:{m:02d}:00"


# ---------------------------------------------------------------------------
# Presentation list builder
# ---------------------------------------------------------------------------

def _build_presentations(
    program: Program,
    day_names: list[str],
    day_dates: list[str],
) -> list[dict]:
    """Convert the programme into the flat presentation list expected by
    the mobile JS code."""
    topic_names = build_topic_display_names(program)
    presentations: list[dict] = []
    pres_id = 1000
    session_counter = 100
    slot_counter = 40000

    for day_prog in program.days:
        day = day_prog.day
        day_name = day_names[day - 1] if day - 1 < len(day_names) else f"Day {day}"
        day_date_str = day_dates[day - 1] if day - 1 < len(day_dates) else ""
        format_day = f"{day_name}, {day_date_str}" if day_date_str else day_name

        for slot in day_prog.slots:
            ts: TimeSlot = slot["time_slot"]
            sessions: list[Session] = slot.get("sessions", [])
            slot_counter += 1
            slot_id = str(slot_counter)

            start_dt = _slot_start_datetime(day, ts, day_dates)

            # Social / break slots
            if ts.kind in (SlotKind.BREAK, SlotKind.LUNCH, SlotKind.DINNER):
                pres_id += 1
                session_counter += 1
                dur_min = ts.duration_minutes
                presentations.append({
                    "ID": str(pres_id),
                    "Abstract ID": str(pres_id),
                    "Title": "",
                    "Session Title": _esc(ts.label or ts.kind.value.title()),
                    "sessionID": str(session_counter),
                    "slotID": slot_id,
                    "SlotStartTime": start_dt,
                    "TimePerPaper": str(dur_min),
                    "social": "1",
                    "FirstAuthor": "",
                    "Affiliation": "",
                    "Author 2 name": None,
                    "Affiliation 2": None,
                    "Author 3 name": None,
                    "Affiliation 3": None,
                    "Authors extra": None,
                    "keyID1": "0",
                    "keyID2": "0",
                    "Room": "",
                    "Chair 1 Name": "",
                    "formatDay": format_day,
                    "formatDate": f"{day_name[:3]} {ts.start} - {ts.end}",
                })
                continue

            # Plenary slots
            if ts.kind == SlotKind.PLENARY:
                pres_id += 1
                session_counter += 1
                dur_min = ts.duration_minutes
                room_name = ""
                if sessions:
                    room_name = sessions[0].room.name if sessions[0].room else ""
                presentations.append({
                    "ID": str(pres_id),
                    "Abstract ID": str(pres_id),
                    "Title": _esc(ts.label or "Plenary"),
                    "Session Title": _esc(ts.label or "Plenary"),
                    "sessionID": str(session_counter),
                    "slotID": slot_id,
                    "SlotStartTime": start_dt,
                    "TimePerPaper": str(dur_min),
                    "social": "0",
                    "FirstAuthor": _esc(ts.speaker) if ts.speaker else "",
                    "Affiliation": "",
                    "Author 2 name": None,
                    "Affiliation 2": None,
                    "Author 3 name": None,
                    "Affiliation 3": None,
                    "Authors extra": None,
                    "keyID1": "0",
                    "keyID2": "0",
                    "Room": _esc(room_name),
                    "Chair 1 Name": _esc(ts.chair) if ts.chair else "",
                    "formatDay": format_day,
                    "formatDate": f"{day_name[:3]} {ts.start} - {ts.end}",
                })
                continue

            # Regular session slots
            if ts.kind != SlotKind.SESSION:
                continue

            for sess in sessions:
                session_counter += 1
                sess_id_str = str(session_counter)
                room_name = sess.room.name if sess.room else ""
                chair_name = sess.chair.name if sess.chair else ""
                topic_name = topic_names.get(sess.session_id, sess.topic.name if sess.topic else "")
                sess_label = sess.label or topic_name or sess.session_id

                if not sess.papers:
                    # Empty session placeholder
                    pres_id += 1
                    presentations.append({
                        "ID": str(pres_id),
                        "Abstract ID": str(pres_id),
                        "Title": "(no papers)",
                        "Session Title": _esc(sess_label),
                        "sessionID": sess_id_str,
                        "slotID": slot_id,
                        "SlotStartTime": start_dt,
                        "TimePerPaper": str(ts.duration_minutes),
                        "social": "0",
                        "FirstAuthor": "",
                        "Affiliation": "",
                        "Author 2 name": None,
                        "Affiliation 2": None,
                        "Author 3 name": None,
                        "Affiliation 3": None,
                        "Authors extra": None,
                        "keyID1": "0",
                        "keyID2": "0",
                        "Room": _esc(room_name),
                        "Chair 1 Name": _esc(chair_name),
                        "formatDay": format_day,
                        "formatDate": f"{day_name[:3]} {ts.start} - {ts.end}",
                    })
                    continue

                pres_dur = ts.duration_minutes // max(len(sess.papers), 1)
                # Parse start time for per-paper timing
                h_start, m_start = (int(x) for x in ts.start.replace(".", ":").split(":"))
                paper_cursor = h_start * 60 + m_start

                for paper in sess.papers:
                    pres_id += 1
                    authors = paper.authors
                    first_author = _esc(authors[0].name) if authors else ""
                    first_aff = _esc(authors[0].affiliation) if authors else ""
                    a2_name = _esc(authors[1].name) if len(authors) > 1 else None
                    a2_aff = _esc(authors[1].affiliation) if len(authors) > 1 else None
                    a3_name = _esc(authors[2].name) if len(authors) > 2 else None
                    a3_aff = _esc(authors[2].affiliation) if len(authors) > 2 else None
                    extra_authors = None
                    if len(authors) > 3:
                        extra_authors = _esc(
                            ", ".join(a.name for a in authors[3:] if a.name)
                        )

                    # Compute per-paper start datetime
                    ph, pm = divmod(paper_cursor, 60)
                    paper_start_dt = _slot_start_datetime(
                        day,
                        TimeSlot(
                            start=f"{ph:02d}:{pm:02d}",
                            end=ts.end,
                            kind=ts.kind,
                            day=day,
                        ),
                        day_dates,
                    )

                    pref1 = str(paper.pref_ids[0]) if paper.pref_ids else "0"
                    pref2 = str(paper.pref_ids[1]) if len(paper.pref_ids) > 1 else "0"

                    presentations.append({
                        "ID": str(pres_id),
                        "Abstract ID": str(paper.paper_id),
                        "Title": _esc(paper.title),
                        "Session Title": _esc(sess_label),
                        "sessionID": sess_id_str,
                        "slotID": slot_id,
                        "SlotStartTime": paper_start_dt,
                        "TimePerPaper": str(pres_dur),
                        "social": "0",
                        "FirstAuthor": first_author,
                        "Affiliation": first_aff,
                        "Author 2 name": a2_name,
                        "Affiliation 2": a2_aff,
                        "Author 3 name": a3_name,
                        "Affiliation 3": a3_aff,
                        "Authors extra": extra_authors,
                        "keyID1": pref1,
                        "keyID2": pref2,
                        "Room": _esc(room_name),
                        "Chair 1 Name": _esc(chair_name),
                        "formatDay": format_day,
                        "formatDate": f"{day_name[:3]} {ts.start} - {ts.end}",
                    })

                    paper_cursor += pres_dur

    return presentations


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_CSS = """\
body { font-family: Arial, sans-serif; }
table { border-collapse: collapse; }
.mainTitle { text-align: center; padding-top: 60px; }
.infoPres { margin: 5px 20px; font-size: small; }
.author { color: #a00; }
.presTitle { color: #00a; margin-bottom: 2px; }
.maxPapersP { margin-top: 2px; font-size: small; color: #444; }
.highlightPres { background-color: #eee; }
.roomName { font-weight: normal; color: #777; }
.chairperson { font-weight: bold; font-size: small; }
.linkAbstract { color: blue; }
.favText { color: blue; }
.favPres { border-right: #fd0 12px solid; }
.nextup { border-left: orange 12px solid; }
.ongoing { border-left: #0d0 12px solid; }
.allmostfinished { border-left: #f44 12px solid; }
a:link { text-decoration: none; }
a:hover { text-decoration: underline; }
"""

_JS = r"""
var urlGET = new URLSearchParams(location.search);
if (urlGET.get('edit') == '1') { editable = true; } else { editable = false; }

function getCookieFavIDs(){
    let ca = document.cookie.split(';');
    for(let i = 0; i < ca.length; i++) {
        let c = ca[i].trim();
        if (c.indexOf("favIDs=") == 0) {
            return c.substring(7, c.length);
        }
    }
    return "[]";
}

const favIDs = new Set(JSON.parse(getCookieFavIDs()));

var timeOutID = null;

function setOngoing(){
    currTimeMS = Date.now();
    nextEvent = currTimeMS + 30000000;
    delayNextup = 180000;
    for (const pres of allPresentations){
        if ((pres.presStartMS <= currTimeMS) && (pres.presStopMS > currTimeMS)){
            $(".presentationRow").filter("[data-presID='" + pres.ID + "']")
                .addClass("ongoing").addClass("keepvisible").show().removeClass("nextup")
                .attr("data-stopMS",pres.presStopMS);
            delay = pres.presStopMS - currTimeMS;
            nextEvent = Math.min(delay,nextEvent);
        }
        else if ((pres.presStartMS <= currTimeMS + delayNextup) && (pres.presStopMS > currTimeMS)){
            $(".presentationRow").filter("[data-presID='" + pres.ID + "']")
                .addClass("nextup").addClass("keepvisible").show();
            delay = pres.presStartMS - currTimeMS;
            nextEvent = Math.min(delay,nextEvent);
        }
        else if (pres.presStartMS > currTimeMS + delayNextup){
            delay = pres.presStartMS - currTimeMS - delayNextup;
            nextEvent = Math.min(delay,nextEvent);
        }
    }
    $(".ongoing").each(function(){
        if ($(this).attr("data-stopMS") <= currTimeMS){
            $(this).removeClass("ongoing").removeClass('keepvisible').removeClass(".allmostfinished");
            if ((!$(this).prevUntil(".sessionHeadRow").filter(".chairRow").is(":visible")) && (!$(this).is(".favPres"))){
                $(this).hide();
            }
        }
        else if ($(this).attr("data-stopMS") <= currTimeMS + delayNextup){
            $(this).removeClass("keepvisible").removeClass("ongoing").addClass("allmostfinished");
            if ((!$(this).prevUntil(".sessionHeadRow").filter(".chairRow").is(":visible")) && (!$(this).is(".favPres"))){
                $(this).hide();
            }
        }
        else{
            delay = $(this).attr("data-stopMS") - currTimeMS;
            nextEvent = Math.min(delay,nextEvent);
        }
    });
    $(".allmostfinished").each(function(){
        if ($(this).attr("data-stopMS") <= currTimeMS){
            $(this).removeClass("allmostfinished");
        }
    });
    if (timeOutID != null){ clearTimeout(timeOutID); }
    timeOutID = setTimeout(setOngoing,nextEvent);
}

$(document).ready(function(){
    slotID = 0;
    sessionID = 0;
    cformatday = new Date(0);

    for (const pres of allPresentations){
        if (slotID != pres.slotID){
            slotDate = new Date(pres.SlotStartTime.split(" ")[0]);
            if (pres.formatDay != cformatday){
                cformatday = pres.formatDay;
                $("#cdiv").append("<hr />")
                    .append($("<h2>" + pres.formatDay + "</h2>").css('margin-top','80px'));
            }
            if (pres.social == "1"){
                $("#cdiv").append("<div class=\"w3-container w3-text-theme\"><h3>" + pres.formatDate + " - " + pres["Session Title"]+ "</h3></div>");
                slotID = pres.slotID;
                continue;
            }
            slotID = pres.slotID;
            $("#cdiv").append("<div class=\"w3-container w3-theme-dark\"><h3>" + pres.formatDate + "</h3></div>");
            room = 1;
            slotTable = $("<table></table>").addClass("w3-table");
            $("#cdiv").append(slotTable);
        }

        if (sessionID != pres.sessionID){
            nrPaper = 1;
            sessionID = pres.sessionID;
            var presTime = new Date(pres.SlotStartTime.replace(" ","T"));
            sessionRow = $("<tr></tr>");
            slotTable.append(sessionRow);
            sessionRow
                .append("<th>"+ pres["Session Title"] + "</th>")
                .append("<td>"+ pres.Room+ "</td>")
                .addClass("sessionHeadRow")
                .addClass("w3-border-top")
                .attr("data-ID",pres.sessionID);
            if (pres.social == "1"){
                sessionRow.addClass("w3-text-theme");
            }else{
                sessionRow.addClass("w3-theme");
            }
            chairRow = $("<tr class=\"w3-small\"></tr>")
                .append("<td colspan=\"2\">Chair: <span class=\"w3-serif\">" + pres['Chair 1 Name'] + "</span></td>")
                .addClass("presentationRow w3-theme-l3 chairRow")
                .attr("data-sessionID",pres.sessionID);
            slotTable.append(chairRow.hide());
        }

        presRow = $("<tr></tr>");
        presRow.hide();
        slotTable.append(presRow);
        presRow.append("<td colspan=\"2\"><span class=\"w3-monospace\">"+ presTime.getHours()+":"+String(presTime.getMinutes()).padStart(2,"0") + "</span> - " + pres.FirstAuthor + " - <span class=\"w3-small w3-serif\">" + pres.Affiliation + "</span><br /><span class=\"w3-small\">" + pres.Title +"</span></td>")
            .addClass("presentationRow")
            .addClass("w3-theme-l4 w3-border-top")
            .attr("data-sessionID",pres.sessionID)
            .attr("data-presID",pres.ID);

        authorsBisRow = $("<tr></tr>")
            .addClass("authorsRow")
            .addClass("w3-theme-l5")
            .attr("data-sessionID",pres.sessionID)
            .attr("data-presID",pres.ID);
        authorsBisRow.hide();
        slotTable.append(authorsBisRow);
        authorsBisTD = $("<td class=\"w3-small\"></td>");
        affiliationsBisTD = $("<td class=\"w3-small\"></td>");
        authorsBisRow.append(authorsBisTD).append(affiliationsBisTD);

        if (pres['Author 2 name'] != null){
            authorsBisTD.append(pres['Author 2 name']);
            affiliationsBisTD.append(pres['Affiliation 2']);
        }
        if (pres['Author 3 name'] != null){
            authorsBisTD.append('<br />' + pres['Author 3 name']);
            affiliationsBisTD.append('<br />' + pres['Affiliation 3']);
        }
        if (pres['Authors extra'] != null){
            authorsBisTD.append('<br />' + pres['Authors extra']);
        }

        favCB = $("<input></input>").attr("type","checkbox")
            .addClass("favCB")
            .attr("data-presID",pres.ID);
        affiliationsBisTD.append("<br />")
            .append(favCB)
            .append(" <span class=\"favText\">Add to favorites</span>");

        pres.presStartMS = presTime.getTime();
        presTime.setMinutes(presTime.getMinutes() + Number(pres.TimePerPaper));
        pres.presStopMS = presTime.getTime();
    }

    $(".sessionHeadRow").click(function(){
        thePresRow = $(".presentationRow").filter("[data-sessionID='"+$(this).attr("data-ID")+"']");
        if (thePresRow.is(":visible")){
            $(".authorsRow").filter("[data-sessionID='"+thePresRow.attr("data-sessionID")+"']").hide(250);
        }
        thePresRow.each(function(){
            if ((!$(this).is(".keepvisible")) && (!$(this).is(".favPres"))){
                $(this).toggle(250);
            }
        });
    });

    $(".presentationRow").click(function(){
        $(".authorsRow").filter("[data-presID='"+$(this).attr("data-presID")+"']").toggle(250);
    });

    $(".presentationRow").hide(function(){
        $(".authorsRow").filter("[data-presID='"+$(this).attr("data-presID")+"']").hide(250);
    });

    $(".favCB").change(function(){
        presID = $(this).attr("data-presID");
        thisPresRow = $(".presentationRow").filter("[data-presID='"+ presID +"']");
        if ($(this)[0].checked){
            thisPresRow.addClass("favPres").show();
            favIDs.add(presID);
        }else{
            thisPresRow.removeClass("favPres");
            if (!thisPresRow.prevUntil(".sessionHeadRow").filter(".chairRow").is(":visible")){
                if (!thisPresRow.is(".keepvisible")){
                    thisPresRow.hide();
                    thisPresRow.next().hide();
                }
            }
            favIDs.delete(presID);
        }
        favArr = new Array();
        for (const x of favIDs){favArr.push(x);}
        document.cookie = "favIDs=" + JSON.stringify(favArr) + "; expires=Sun, 1 Jan 2028 12:00:00 UTC";
    });

    $("#clearFavs").click(function(){
        if (!confirm("Clear favorites?\nThis cannot be undone!")){ return; }
        $(".favCB").each(function(){
            if ($(this)[0].checked){ $(this).click(); }
        });
        document.cookie = "favIDs=; expires=Thu, 01 Jan 1970 00:00:00 UTC;";
    });

    $("#expandAll").click(function(){ $(".presentationRow").show(); });
    $("#collapseAll").click(function(){
        $(".presentationRow").not(".keepvisible").not(".favPres").hide();
        $(".authorsRow").hide();
    });

    for (const fID of favIDs){
        $(".favCB").filter("[data-presID='"+ fID +"']").click();
    }

    setOngoing();
    setInterval(setOngoing, 30000);

    if (urlGET.get('sessionID') != null){
        scrollSessionID = urlGET.get('sessionID');
        var el = document.getElementById("session" + scrollSessionID);
        if (el) el.scrollIntoView();
    }
    if (urlGET.get('abstractID') != null){
        scrollAbstractID = urlGET.get('abstractID');
        var el = document.getElementById("abstract" + scrollAbstractID);
        if (el) el.scrollIntoView();
    }
});
"""


def _html_template(
    title: str,
    subtitle: str,
    edition: str,
    date_text: str,
    venue: str,
    presentations_json: str,
) -> str:
    """Return the full HTML document."""
    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(edition)} {_esc(title)} {_esc(subtitle)} — Programme</title>
<link rel="stylesheet" href="https://www.w3schools.com/w3css/4/w3pro.css">
<link rel="stylesheet" href="https://www.w3schools.com/lib/w3-theme-blue.css">
<style>
{_CSS}
</style>
<script src="https://ajax.googleapis.com/ajax/libs/jquery/3.4.1/jquery.min.js"></script>
<script>

allPresentations = {presentations_json};

{_JS}

</script>
</head>
<body>

<div class="w3-container mainTitle">
<h1 class="w3-serif">{_esc(edition)} {_esc(title)}<br />{_esc(subtitle)}</h1>
<p style="margin-top:50px;margin-bottom:30px">
{_esc(date_text)}<br />
{_esc(venue)}
</p>
<h2 class="w3-serif" style="margin-bottom:50px;">Conference programme</h2>
</div>

<hr />

<div class="w3-container">
<p><a id="expandAll" href="#">Expand all</a> - <a id="collapseAll" href="#">Collapse all</a></p>
</div>

<div id="cdiv" class="w3-container">
</div>

<div class="w3-container">
<p>
Your favorites are stored on your browser as a cookie, and are only available to you, on this device.
<br />
<a href="#" id="clearFavs">Clear favorites</a>
</p>
</div>

</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_mobile_html(
    program: Program,
    output_path: str | Path,
    latex_config: Optional[str | Path] = None,
    *,
    conference_title: str = "Conference",
    conference_subtitle: str = "",
    edition: str = "",
    date_text: str = "",
    venue: str = "",
    day_names: Optional[list[str]] = None,
    day_dates: Optional[list[str]] = None,
) -> None:
    """Write a self-contained mobile HTML programme page.

    If *latex_config* is provided, conference metadata is read from it
    (same format as for the LaTeX folder output).  Explicit keyword
    arguments override values from the config file.
    """
    # Load metadata from latex config if available
    if latex_config and Path(latex_config).exists():
        raw = json.loads(Path(latex_config).read_text())
        conference_title = conference_title if conference_title != "Conference" else raw.get("conference_title", conference_title)
        conference_subtitle = conference_subtitle or raw.get("conference_subtitle", "")
        edition = edition or raw.get("edition", "")
        date_text = date_text or raw.get("date_text", "")
        venue = venue or raw.get("venue", "")
        if day_names is None:
            day_names = raw.get("day_names", [])
        if day_dates is None:
            day_dates = raw.get("day_dates", [])

    if day_names is None:
        day_names = []
    if day_dates is None:
        day_dates = []

    # Fill in default day names if not provided
    if not day_names:
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_names = [weekdays[(d - 1) % 7] for d in range(1, len(program.days) + 1)]

    presentations = _build_presentations(program, day_names, day_dates)
    pres_json = json.dumps(presentations, ensure_ascii=False)

    page = _html_template(
        title=conference_title,
        subtitle=conference_subtitle,
        edition=edition,
        date_text=date_text,
        venue=venue,
        presentations_json=pres_json,
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
