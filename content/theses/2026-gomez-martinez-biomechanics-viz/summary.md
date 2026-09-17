CHLOE (Clinical Helper for Locomotion Objective Evaluation) is a browser-based
tool for visualising and analysing biomechanical motion-capture data. It reads
the C3D files produced by biomechanics laboratories and renders them without
the specialised, hard-to-configure software such data normally demands,
concentrating instead on the tasks physiotherapists actually perform in
clinical practice. It recognises the Plug-in Gait marker protocol
automatically but is not limited to it, visualising arbitrary marker sets so
that data from optical motion capture, low-cost inertial sensors and XR
headsets can all be inspected in the same place.

Technically, Python and the ezc3d library convert binary C3D into JSON, which
a Three.js engine renders as animated point clouds, dynamic skeletons and
mapped 3D avatars, while Plotly.js draws interactive graphs of user-selected
channels — including analog signals such as electromyography and ground
reaction forces. The application is deployed as Docker containers for
portability, and was validated through usability testing with physiotherapy
professionals, who confirmed its value in both clinical and educational
settings. CHLOE forms part of the LibreMotion project, whose aim is to make
the capture, storage and analysis of biomechanical data accessible using
low-cost equipment.
