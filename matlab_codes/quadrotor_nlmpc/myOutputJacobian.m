function C = myOutputJacobian(x,u)
C = zeros(3,4);
C(1,1) = 1;
C(2,2) = 1;
C(2,3) = 0.2;
C(3,3) = x(4);
C(3,4) = x(3);
C = zeros(3,4);
C(1,1) = 1;
C(2,2) = 1;
C(2,3) = 0.2;
C(3,3) = x(4);
C(3,4) = x(3);