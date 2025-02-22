import tkinter as ttk
import json,time,socket
import threading,cv2,io
import numpy as np
import matplotlib.pyplot as plt
from PIL import ImageTk, Image

RPI_ADDRESS = ('192.168.10.11', 32152)  # IP of Robot RPi
UDP_IP_ROBOT = ("192.168.10.11",5006)  # Replace with the actual IP address of your robot

UDP_IP_EDGE = ("195.54.97.118",5005)  # IP of the EDGE so that camera angle could be sent
UDP_IP_EDGE_NEAR = ("192.168.10.219",5007)  # IP of the NEAR EDGE (hosts) so that camera angle could be sent
UDP_IP_EDGE_LOCAL = ("192.168.10.219",5006)  # This hosts IP to listen controller command

VIDEO_SAVE_PATH = 'captured_video.avi'  # Specify the path where you want to save the video
class UI():
    def __init__(self, root):
        self.root = root
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Container for all widgets
        self.container = ttk.Frame(root)
        self.container.pack(fill=ttk.BOTH, expand=True)

        # First row with two big frames
        self.frame1 = ttk.Frame(self.container, width=200, height=200, relief=ttk.RIDGE, borderwidth=2)
        self.frame1.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Second row with button and slider
        button_frame = ttk.Frame(self.container)
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)

        self.confirm_button = ttk.Button(button_frame, text="Confirm Angle", command=self.confirm_angle, background='gray')
        self.confirm_button.pack(side=ttk.LEFT, padx=10)

        slider_frame = ttk.Frame(button_frame)
        slider_frame.pack(side=ttk.LEFT, padx=10)

        self.stop_button = ttk.Button(button_frame, text="Stop Motion", command=self.stop_motion)
        self.stop_button.pack(side=ttk.LEFT, padx=10)

        self.slider_label = ttk.Label(slider_frame, text="Motor Power: 0")
        self.slider_label.pack(side=ttk.TOP)

        self.slider = ttk.Scale(slider_frame, from_=-100, to=100, length=300, orient=ttk.HORIZONTAL, command=self.update_slider_label)
        self.slider.pack(side=ttk.TOP)

        # Start capturing video from the default camera
        self.cap = cv2.VideoCapture(0)
        self.start_time = time.time()
        self.time_data = []
        self.error_data = []
        self.desired_angle = 0
        self.motion_check = 1
        self.control_check = 0
        # Canvas for displaying video feed
        self.canvas = ttk.Canvas(self.frame1, width=self.cap.get(cv2.CAP_PROP_FRAME_WIDTH), height=self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.canvas.pack()

        # Camera capture thread
        self.camera_thread = threading.Thread(target=self.camera_capture)
        self.camera_thread.start()


        # Motion thread
        self.motion_thread = threading.Thread(target=self.motion)
        self.motion_thread.start()
        self.server_to_listen = ''

        self.time_measurements = []
    def __del__(self):
        if self.cap.isOpened():
            self.cap.release()
    def camera_capture(self):
        id = 0
        
        try:
            # Read the template image
            image_template = cv2.imread('sample.png')

            # Convert the template image to grayscale
            templ_gray = image_template

            # Start capturing video from the default camera
            cap = cv2.VideoCapture(0)

            # Get the video frame width and height 
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(frame_width, frame_height)
            # Define the codec and create VideoWriter object
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            out = cv2.VideoWriter(VIDEO_SAVE_PATH, fourcc, 20.0, (frame_width, frame_height))
            lower_line = 150
            while True:
                # Capture a frame from the video
                a = time.time()
                ret, frame = cap.read()
                if not ret:
                    print("Failed to capture frame")
                    break
                
                # Split the frame into two halves vertically
                half_height = frame_height // 2
                upper_half = frame[:half_height, :]
                lower_half = frame[half_height:-lower_line, :]

                # Convert the captured frames to grayscale
                upper_gray = upper_half
                lower_gray = lower_half

                # Match template for upper half
                result_upper = cv2.matchTemplate(upper_gray, templ_gray, cv2.TM_CCORR_NORMED)

                # Match template for lower half
                result_lower = cv2.matchTemplate(lower_gray, templ_gray, cv2.TM_CCORR_NORMED)

                # Find locations of the best matches for upper half
                _, _, _, max_loc1 = cv2.minMaxLoc(result_upper)
                _, _, _, max_loc2 = cv2.minMaxLoc(result_lower)

                # Store coordinates of detected objects in the upper half (tip point)
                tip_point = {'x': max_loc1[0] + templ_gray.shape[1] // 2, 'y': max_loc1[1] + templ_gray.shape[0] // 2}

                # Store coordinates of detected objects in the lower half (fixed point)
                fixed_point = {'x': max_loc2[0] + templ_gray.shape[1] // 2, 'y': max_loc2[1] + templ_gray.shape[0] // 2 + half_height}

                # Draw a big dot at the center of the detected object (tip point) and display its coordinates
                for coord in [tip_point, fixed_point]:
                    x, y = coord['x'], coord['y']
                    cv2.circle(frame, (x, y), radius=10, color=(0, 255, 0), thickness=-1)  # Draw filled circle
                    cv2.putText(frame, f'({x}, {y})', (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

                # Draw a horizontal line in the middle of the frame
                cv2.line(frame, (0, half_height), (frame_width, half_height), (0, 0, 255), 2)
                cv2.line(frame, (0, frame_height-lower_line), (frame_width, frame_height-lower_line), (0, 0, 255), 2)
                # Calculate the angle between the two detected objects
                dx = tip_point['x'] - fixed_point['x']
                dy = fixed_point['y'] - tip_point['y']
                length = np.sqrt(dx**2 + dy**2)
                angle = 180-np.arccos(dx / length) * 180 / np.pi  # Convert radians to degrees
                #print(f"angle:{angle}")
                # Draw line connecting the two points
                cv2.line(frame, (fixed_point['x'], fixed_point['y']), (tip_point['x'], tip_point['y']), (255, 0, 0), 2)

                # Show the angle between the two points
                cv2.putText(frame, f'Angle: {angle:.2f}', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
                self.angle = angle
                # Write the frame to the video file
                out.write(frame)
                average_time = 1
                if self.control_check:
                # Get user input for the control signal
                    try:
                        # Send control signal over UDP to Raspberry Pi
                        message = {'motor_angle': round(angle), 'id': id,'active':self.control_check}
                        message = json.dumps(message).encode('utf-8')
                        message_m = {'motor_angle': round(angle), 'id': id,'active':0}
                        message_m = json.dumps(message_m).encode('utf-8')
                        # Calculate the average of the last 20 elements, or all elements if less than 20
                        last_20_measurements = self.time_measurements[-20:]  # Get the last 20 elements
                        total_measurements = len(last_20_measurements)

                        # Calculate the average
                        if total_measurements > 0:
                            average_time = sum(last_20_measurements) / total_measurements
                        else:
                            average_time = 1 # Handle case when there are no measurements

                        if average_time >= 0.0033: 
                            self.server_to_listen = UDP_IP_EDGE_NEAR[0]
                            self.server.sendto(message, UDP_IP_EDGE_NEAR)
                            self.server.sendto(message_m, UDP_IP_EDGE)
                        else:
                            self.server_to_listen = UDP_IP_EDGE[0]
                            self.server.sendto(message, UDP_IP_EDGE)
                            self.server.sendto(message_m, UDP_IP_EDGE_NEAR)
                        print(average_time)
                        #self.plot_data()
                        #print(message)
                    except KeyboardInterrupt:
                        print("Exiting program")
                        self.server.close()
                else:
                    # Send control signal over UDP to Raspberry Pi
                    message = {'motor_angle': round(angle), 'id': id,'active':self.control_check}
                    message = json.dumps(message).encode('utf-8')
                    self.server.sendto(message, UDP_IP_EDGE_NEAR)
                    self.server.sendto(message, UDP_IP_EDGE)
                id += 1
                # Convert the frame to RGB format
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Resize the frame to fit the canvas if needed
                resized_frame = cv2.resize(frame_rgb, (self.canvas.winfo_width(), self.canvas.winfo_height()))
                
                # Convert the resized frame to ImageTk format
                photo = ImageTk.PhotoImage(image=Image.fromarray(resized_frame))

                # Update the canvas with the new frame
                self.canvas.create_image(0, 0, image=photo, anchor=ttk.NW)

                # Keep a reference to the photo to prevent it from being garbage collected
                self.canvas.photo = photo

                # Check for 'q' key press to exit
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            # Release the video capture object, release the VideoWriter object, and close all windows
            cap.release()
            out.release()
            cv2.destroyAllWindows()

        except Exception as e:
            print(e)


    def confirm_angle(self):
        
        # Toggle button color between green and default color
        current_color = self.confirm_button.cget('background')
        if current_color == 'green':
            self.confirm_button.config(background='gray')
            result = {"control_signal":0}
            print(result)
            message = json.dumps(result).encode('utf-8')
            self.server.sendto(message, UDP_IP_ROBOT)
            self.control_check = 0
            print("Control stopped...")
        else:
            self.confirm_button.config(background='green')
            self.control_check = 1
            print("Control started...")
            self.desired_angle = self.angle
            # Pendulum Controll
            self.control_thread = threading.Thread(target=self.control_signal)
            self.control_thread.start()
        self.desired_angle = self.angle

    def stop_motion(self):
        
        # Toggle button color between green and default color
        current_color = self.stop_button.cget('background')
        if current_color == 'green':
            self.stop_button.config(background='gray')
        else:
            self.stop_button.config(background='gray')
           
        if not(self.motion_check): 
            self.sock.close()
        else:
            result = {"PacketType": 'ControlMessage', 'PowerValue': 0,"direction":RPI_ADDRESS}
            print(result)
            message = json.dumps(result).encode('utf-8')
            self.sock.sendto(message, RPI_ADDRESS)  
        self.motion_check = 0
        print("Stop Motion Confirmed")

    def update_slider_label(self,event):
        self.slider_label.config(text=f"Motor Power: {self.slider.get() // 1}")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.motion_check == 0:
            self.motion_check = 1
            self.t1 = threading.Thread(target=self.motion)
            self.t1.start()

    def motion(self):
        while self.motion_check:
            #print("HERE")
            result = {"PacketType": 'ControlMessage', 'PowerValue': self.slider.get(),"direction":RPI_ADDRESS}
            #print(result)
            message = json.dumps(result).encode('utf-8')
            self.sock.sendto(message, RPI_ADDRESS)
            time.sleep(.1)
            
    def control_signal(self):
        while self.control_check:
            mem = time.time()
            # Receive the control signal from Edge
            try:
                data,addr = self.server.recvfrom(4096)
            except KeyboardInterrupt:
                break
            
            if addr[0] == UDP_IP_EDGE[0]:
                self.time_measurements.append(time.time()-mem)

            if self.control_check:
                if addr[0] == self.server_to_listen:
                    message = json.loads(data.decode('utf-8'))
                    result = {"control_signal":message['control_signal']}
                    print(result,addr)
                    message = json.dumps(result).encode('utf-8')
                    self.server.sendto(message, UDP_IP_ROBOT)
            else:
                message = json.loads(data.decode('utf-8'))
                result = {"control_signal":0}
                self.time_measurements = []
                #print(result)
                message = json.dumps(result).encode('utf-8')
                self.server.sendto(message, UDP_IP_ROBOT)
            #time.sleep(.1)

root = ttk.Tk()
root.title("UI Layout")

ui = UI(root=root)
root.mainloop()



