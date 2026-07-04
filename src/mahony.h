#ifndef MAHONY_H
#define MAHONY_H
#include <math.h>

extern float q0, q1, q2, q3; // Quaternion

void MahonyAHRSupdateIMU(float gx, float gy, float gz, float ax, float ay, float az, float dt);

#endif
