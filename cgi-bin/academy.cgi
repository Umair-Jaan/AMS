#!/usr/bin/env python3
import cgi
import os
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "academy_data.txt"

print("Content-Type: text/html; charset=utf-8")
print()

form = cgi.FieldStorage()
roll = form.getvalue("roll", "")
name = form.getvalue("name", "")
class_level = form.getvalue("class_level", "")
gender = form.getvalue("gender", "")
section = form.getvalue("section", "")
phone = form.getvalue("phone", "")
remarks = form.getvalue("remarks", "")

if roll and name:
    with DATA_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{roll}|{name}|{class_level}|{gender}|{section}|{phone}|{remarks}\n")

print("<!doctype html>")
print("<html><head><meta charset='utf-8'><title>Academy Management</title>")
print("<link rel='stylesheet' href='../style.css'></head><body>")
print("<main class='container'><h1>Academy Management</h1>")
if roll and name:
    print("<p>Student saved successfully.</p>")
print("<form action='academy.cgi' method='post'>")
print("<label>Roll number</label><input name='roll' required>")
print("<label>Name</label><input name='name' required>")
print("<label>Class level</label><input name='class_level' type='number' min='9' max='12' required>")
print("<label>Gender</label><select name='gender'><option value='boys'>Boys</option><option value='girls'>Girls</option></select>")
print("<label>Section</label><input name='section'>")
print("<label>Phone</label><input name='phone'>")
print("<label>Remarks</label><textarea name='remarks'></textarea>")
print("<button type='submit'>Save student</button></form>")
print("<h2>Saved students</h2>")
if DATA_FILE.exists():
    print("<ul>")
    for line in DATA_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            print(f"<li>{line}</li>")
    print("</ul>")
print("</main></body></html>")
