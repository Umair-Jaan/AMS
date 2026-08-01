#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DATA_FILE "academy_data.txt"

typedef struct {
    char roll[32];
    char name[64];
    int class_level;
    char gender[16];
    char section[16];
    char phone[32];
    char remarks[128];
} Student;

static char *url_decode(const char *src) {
    static char buffer[512];
    size_t i, j;
    if (src == NULL) {
        buffer[0] = '\0';
        return buffer;
    }
    for (i = 0, j = 0; src[i] != '\0' && j < sizeof(buffer) - 1; ++i) {
        if (src[i] == '+') {
            buffer[j++] = ' ';
        } else if (src[i] == '%' && isxdigit((unsigned char)src[i + 1]) && isxdigit((unsigned char)src[i + 2])) {
            char hex[3] = {src[i + 1], src[i + 2], '\0'};
            buffer[j++] = (char)strtol(hex, NULL, 16);
            i += 2;
        } else {
            buffer[j++] = src[i];
        }
    }
    buffer[j] = '\0';
    return buffer;
}

static void parse_form_data(const char *data, Student *student) {
    char *copy = strdup(data ? data : "");
    char *token = strtok(copy, "&");
    memset(student, 0, sizeof(*student));

    while (token != NULL) {
        char *separator = strchr(token, '=');
        if (separator != NULL) {
            *separator = '\0';
            char *key = url_decode(token);
            char *value = url_decode(separator + 1);

            if (strcmp(key, "roll") == 0) {
                strncpy(student->roll, value, sizeof(student->roll) - 1);
            } else if (strcmp(key, "name") == 0) {
                strncpy(student->name, value, sizeof(student->name) - 1);
            } else if (strcmp(key, "class_level") == 0) {
                student->class_level = atoi(value);
            } else if (strcmp(key, "gender") == 0) {
                strncpy(student->gender, value, sizeof(student->gender) - 1);
            } else if (strcmp(key, "section") == 0) {
                strncpy(student->section, value, sizeof(student->section) - 1);
            } else if (strcmp(key, "phone") == 0) {
                strncpy(student->phone, value, sizeof(student->phone) - 1);
            } else if (strcmp(key, "remarks") == 0) {
                strncpy(student->remarks, value, sizeof(student->remarks) - 1);
            }
        }
        token = strtok(NULL, "&");
    }
    free(copy);
}

static int save_student(const Student *student) {
    FILE *fp = fopen(DATA_FILE, "a");
    if (!fp) {
        return 0;
    }
    fprintf(fp, "%s|%s|%d|%s|%s|%s|%s\n",
            student->roll,
            student->name,
            student->class_level,
            student->gender,
            student->section,
            student->phone,
            student->remarks);
    fclose(fp);
    return 1;
}

static void print_students_html(void) {
    FILE *fp = fopen(DATA_FILE, "r");
    printf("<h2>Saved students</h2>\n");
    if (!fp) {
        printf("<p>No students saved yet.</p>\n");
        return;
    }

    printf("<ul>\n");
    char line[512];
    while (fgets(line, sizeof(line), fp) != NULL) {
        if (line[0] == '\0') {
            continue;
        }
        printf("<li>%s</li>\n", line);
    }
    printf("</ul>\n");
    fclose(fp);
}

static void print_page(const char *message) {
    printf("Content-Type: text/html; charset=utf-8\r\n\r\n");
    printf("<!doctype html><html><head><meta charset='utf-8'><title>Academy CGI</title>");
    printf("<link rel='stylesheet' href='../style.css'></head><body>");
    printf("<main class='container'><h1>Academy Management</h1>");
    if (message && message[0] != '\0') {
        printf("<p>%s</p>", message);
    }
    printf("<form action='academy.cgi' method='post'>");
    printf("<label>Roll number</label><input name='roll' required>");
    printf("<label>Name</label><input name='name' required>");
    printf("<label>Class level</label><input name='class_level' type='number' min='9' max='12' required>");
    printf("<label>Gender</label><select name='gender'><option value='boys'>Boys</option><option value='girls'>Girls</option></select>");
    printf("<label>Section</label><input name='section'>");
    printf("<label>Phone</label><input name='phone'>");
    printf("<label>Remarks</label><textarea name='remarks'></textarea>");
    printf("<button type='submit'>Save student</button></form>");
    print_students_html();
    printf("</main></body></html>\n");
}

int main(void) {
    char *method = getenv("REQUEST_METHOD");
    char *content_length_env = getenv("CONTENT_LENGTH");
    long content_length = content_length_env ? atol(content_length_env) : 0;

    Student student;
    memset(&student, 0, sizeof(student));

    if (method != NULL && strcmp(method, "POST") == 0) {
        char *buffer = malloc(content_length + 1);
        if (!buffer) {
            print_page("Unable to process request.");
            return 1;
        }
        size_t read_count = fread(buffer, 1, (size_t)content_length, stdin);
        buffer[read_count] = '\0';
        parse_form_data(buffer, &student);
        free(buffer);

        if (student.roll[0] != '\0' && student.name[0] != '\0') {
            if (save_student(&student)) {
                print_page("Student saved successfully.");
                return 0;
            }
            print_page("Could not save the student record.");
            return 1;
        }
    }

    print_page("");
    return 0;
}
