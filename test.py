from djitellopy import Tello
import cv2

tello = Tello()


tello.connect()

tello.streamon()

frame = tello.get_frame_read()

while True:
    image = frame.frame
    cv2.imshow("Principal", image)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cv2.destroyAllWindows()
tello.end()